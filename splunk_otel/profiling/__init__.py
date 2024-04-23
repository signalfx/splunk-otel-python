# Copyright Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import atexit
import base64
import gzip
import logging
import os
import sys
import threading
import time
import traceback
from collections import OrderedDict
from traceback import StackSummary
from typing import Dict, Optional, Union

import opentelemetry.context
import wrapt
from opentelemetry._logs import SeverityNumber
from opentelemetry.context import Context
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.sdk._logs import LoggerProvider, LogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.trace import TraceFlags
from opentelemetry.trace.propagation import _SPAN_KEY

from splunk_otel.options import _create_resource
from splunk_otel.profiling import profile_pb2
from splunk_otel.profiling.options import _Options

logger = logging.getLogger(__name__)


class Profiler:
    def __init__(self):
        self.condition = threading.Condition(threading.Lock())
        self.thread_states = {}

        self.resource = None
        self.call_stack_interval_millis = None
        self.include_internal_stacks = None
        self.running = False

        self.logger_provider = None
        self.exporter = None
        self.batch_processor = None

    def setup(
        self, resource, endpoint, call_stack_interval_millis, include_internal_stacks
    ):
        # pylint: disable=import-outside-toplevel
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

        self.resource = resource
        self.call_stack_interval_millis = call_stack_interval_millis
        self.include_internal_stacks = include_internal_stacks
        self.running = True

        self.exporter = OTLPLogExporter(endpoint)
        self.batch_processor = BatchLogRecordProcessor(self.exporter)
        self.logger_provider = LoggerProvider(resource=resource)
        self.logger_provider.add_log_record_processor(self.batch_processor)

    def loop(self):
        ignored_thread_ids = self.get_ignored_thread_ids()

        profiling_logger = self.logger_provider.get_logger("otel.profiling", "0.1.0")

        call_stack_interval_seconds = self.call_stack_interval_millis / 1e3
        # In case the processing takes more than the given interval, default to the smallest allowed interval
        min_call_stack_interval_seconds = 1 / 1e3
        while self.is_running():
            time_begin = time.time()
            timestamp = int(time_begin * 1e9)

            stacktraces = _collect_stacktraces(ignored_thread_ids)

            log_record = self.to_log_record(
                stacktraces,
                timestamp,
            )

            profiling_logger.emit(log_record)

            processing_time = time.time() - time_begin
            wait_for = max(
                call_stack_interval_seconds - processing_time,
                min_call_stack_interval_seconds,
            )

            with self.condition:
                self.condition.wait(wait_for)

        # Hack around batch log processor getting stuck on application exits when the profiling endpoint is not reachable
        # Could be related: https://github.com/open-telemetry/opentelemetry-python/issues/2284
        # pylint: disable-next=protected-access
        self.exporter._shutdown = True
        self.logger_provider.shutdown()
        with self.condition:
            self.condition.notify_all()

    def get_ignored_thread_ids(self):
        if self.include_internal_stacks:
            return []

        ignored_ids = [threading.get_ident()]

        log_processor_thread_id = self.extract_log_processor_thread_id()

        if log_processor_thread_id:
            ignored_ids.append(log_processor_thread_id)

        return ignored_ids

    def extract_log_processor_thread_id(self):
        if hasattr(self.batch_processor, "_worker_thread"):
            # pylint: disable-next=protected-access
            worker_thread = self.batch_processor._worker_thread

            if isinstance(worker_thread, threading.Thread):
                return worker_thread.ident

        return None

    def to_log_record(self, stacktraces, timestamp_unix_nanos):
        encoded = self.get_cpu_profile(stacktraces, timestamp_unix_nanos)
        encoded_profile = base64.b64encode(encoded).decode()

        frame_count = 0
        for stacktrace in stacktraces:
            frame_count += len(stacktrace["frames"])

        return LogRecord(
            timestamp=timestamp_unix_nanos,
            trace_id=0,
            span_id=0,
            trace_flags=TraceFlags(0x01),
            severity_number=SeverityNumber.UNSPECIFIED,
            body=encoded_profile,
            resource=self.resource,
            attributes={
                "profiling.data.format": "pprof-gzip-base64",
                "profiling.data.type": "cpu",
                "com.splunk.sourcetype": "otel.profiling",
                "profiling.data.total.frame.count": frame_count,
            },
        )

    def get_cpu_profile(self, stacktraces, timestamp_unix_nanos):
        str_table = StringTable()
        locations_table = OrderedDict()
        functions_table = OrderedDict()

        def get_function(file_name, function_name):
            key = f"{file_name}:{function_name}"
            fun = functions_table.get(key)

            if fun is None:
                name_id = str_table.index(function_name)
                fun = profile_pb2.Function()
                fun.id = len(functions_table) + 1
                fun.name = name_id
                fun.system_name = name_id
                fun.filename = str_table.index(file_name)
                functions_table[key] = fun

            return fun

        def get_line(file_name, function_name, line_no):
            line = profile_pb2.Line()
            line.function_id = get_function(file_name, function_name).id
            line.line = line_no if line_no != 0 else -1
            return line

        def get_location(frame):
            (file_name, function_name, line_no) = frame
            key = f"{file_name}:{function_name}:{line_no}"
            location = locations_table.get(key)

            if location is None:
                location = profile_pb2.Location()
                location.id = len(locations_table) + 1
                location.line.append(get_line(file_name, function_name, line_no))
                locations_table[key] = location

            return location

        timestamp_unix_millis = int(timestamp_unix_nanos / 1e6)

        timestamp_key = str_table.index("source.event.time")
        trace_id_key = str_table.index("trace_id")
        span_id_key = str_table.index("span_id")
        thread_id_key = str_table.index("thread.id")
        event_period_key = str_table.index("source.event.period")

        pb_profile = profile_pb2.Profile()

        event_period_label = profile_pb2.Label()
        event_period_label.key = event_period_key
        event_period_label.num = self.call_stack_interval_millis

        samples = []
        for stacktrace in stacktraces:
            thread_id = stacktrace["tid"]

            timestamp_label = profile_pb2.Label()
            timestamp_label.key = timestamp_key
            timestamp_label.num = timestamp_unix_millis

            thread_id_label = profile_pb2.Label()
            thread_id_label.key = thread_id_key
            thread_id_label.num = thread_id

            labels = [timestamp_label, event_period_label, thread_id_label]

            trace_context = self.thread_states.get(thread_id)
            if trace_context:
                (trace_id, span_id) = trace_context

                trace_id_label = profile_pb2.Label()
                trace_id_label.key = trace_id_key
                trace_id_label.str = str_table.index(f"{trace_id:016x}")
                labels.append(trace_id_label)

                span_id_label = profile_pb2.Label()
                span_id_label.key = span_id_key
                span_id_label.str = str_table.index(f"{span_id:08x}")
                labels.append(span_id_label)

            sample = profile_pb2.Sample()

            location_ids = []

            for frame in reversed(stacktrace["frames"]):
                location_ids.append(get_location(frame).id)

            sample.location_id.extend(location_ids)
            sample.label.extend(labels)

            samples.append(sample)

        pb_profile.sample.extend(samples)
        pb_profile.string_table.extend(str_table.keys())
        pb_profile.function.extend(list(functions_table.values()))
        pb_profile.location.extend(list(locations_table.values()))

        return gzip.compress(pb_profile.SerializeToString())

    def is_running(self):
        return self.running

    def force_flush(self):
        if self.logger_provider:
            self.logger_provider.force_flush()

    def make_wrapped_context_attach(self):
        def _wrapped_context_attach(wrapped, _instance, args, kwargs):
            token = wrapped(*args, **kwargs)

            maybe_context = args[0] if args else None

            if maybe_context:
                span = maybe_context.get(_SPAN_KEY)

                if span:
                    thread_id = threading.get_ident()
                    context = span.get_span_context()
                    self.thread_states[thread_id] = (
                        context.trace_id,
                        context.span_id,
                    )

            return token

        return _wrapped_context_attach

    def make_wrapped_context_detach(self):
        def _wrapped_context_detach(wrapped, _instance, args, kwargs):
            token = args[0] if args else None

            if token:
                prev = token.old_value
                thread_id = threading.get_ident()
                if isinstance(prev, Context):
                    span = prev.get(_SPAN_KEY)

                    if span:
                        context = span.get_span_context()
                        self.thread_states[thread_id] = (
                            context.trace_id,
                            context.span_id,
                        )
                    else:
                        self.thread_states[thread_id] = None
                else:
                    self.thread_states[thread_id] = None
            return wrapped(*args, **kwargs)

        return _wrapped_context_detach


_profiler = Profiler()


def get_profiler():
    return _profiler


class StringTable:
    def __init__(self):
        self.strings = OrderedDict()

    def index(self, token):
        idx = self.strings.get(token)

        if idx:
            return idx

        idx = len(self.strings)
        self.strings[token] = idx
        return idx

    def keys(self):
        return list(self.strings.keys())


def extract_stack(frame):
    stack = StackSummary.extract(
        traceback.walk_stack(frame), limit=None, lookup_lines=False
    )
    stack.reverse()
    return stack


def _collect_stacktraces(ignored_thread_ids):
    stacktraces = []

    frames = sys._current_frames()

    for thread_id, frame in frames.items():
        if thread_id in ignored_thread_ids:
            continue

        stacktrace_frames = []
        stack = extract_stack(frame)
        for sf in stack:
            stacktrace_frames.append((sf.filename, sf.name, sf.lineno))
        stacktrace = {
            "frames": stacktrace_frames,
            "tid": thread_id,
        }
        stacktraces.append(stacktrace)
    return stacktraces


def _start_profiler_thread(profiler):
    profiler_thread = threading.Thread(
        name="splunk-otel-profiler", target=profiler.loop, daemon=True
    )
    profiler_thread.start()


def _force_flush():
    profiler = get_profiler()
    profiler.force_flush()


def _start_profiling(opts):
    profiler = get_profiler()

    if profiler.is_running():
        logger.warning("profiler already running")
        return

    profiler.setup(
        opts.resource,
        opts.endpoint,
        opts.call_stack_interval_millis,
        opts.include_internal_stacks,
    )

    logger.debug(
        "starting profiling call_stack_interval_millis=%s endpoint=%s",
        opts.call_stack_interval_millis,
        opts.endpoint,
    )
    wrapt.wrap_function_wrapper(
        opentelemetry.context, "attach", profiler.make_wrapped_context_attach()
    )
    wrapt.wrap_function_wrapper(
        opentelemetry.context, "detach", profiler.make_wrapped_context_detach()
    )

    # Windows does not have register_at_fork
    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=lambda: _start_profiler_thread(profiler))
    atexit.register(stop_profiling)

    _start_profiler_thread(profiler)


def start_profiling(
    service_name: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    endpoint: Optional[str] = None,
    call_stack_interval_millis: Optional[int] = None,
):
    resource = _create_resource(service_name, resource_attributes)
    opts = _Options(resource, endpoint, call_stack_interval_millis)
    _start_profiling(opts)


def stop_profiling():
    profiler = get_profiler()
    if not profiler.is_running():
        return

    profiler.running = False
    with profiler.condition:
        # Wake up the profiler thread
        profiler.condition.notify_all()
        # Wait for the profiler thread to exit
        profiler.condition.wait()

    unwrap(opentelemetry.context, "attach")
    unwrap(opentelemetry.context, "detach")
