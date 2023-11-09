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
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.sdk._logs import LoggerProvider, LogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import TraceFlags
from opentelemetry.trace.propagation import _SPAN_KEY

import splunk_otel
from splunk_otel.profiling import profile_pb2
from splunk_otel.profiling.options import _Options

logger = logging.getLogger(__name__)


class Profiler:
    def __init__(self):
        self.condition = threading.Condition(threading.Lock())
        self.running = False
        self.thread_states = {}
        self.logger_provider = None
        self.exporter = None
        self.batch_processor = None
        self.options = None


_profiler = Profiler()


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


def _encode_cpu_profile(stacktraces, timestamp_unix_nanos, interval):
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
    event_period_label.num = interval

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

        trace_context = _profiler.thread_states.get(thread_id)
        if trace_context:
            (trace_id, span_id) = trace_context

            trace_id_label = profile_pb2.Label()
            trace_id_label.key = trace_id_key
            trace_id_label.str = str_table.index(f"{trace_id:#016x}")
            labels.append(trace_id_label)

            span_id_label = profile_pb2.Label()
            span_id_label.key = span_id_key
            span_id_label.str = str_table.index(f"{span_id:#08x}")
            labels.append(span_id_label)

        sample = profile_pb2.Sample()

        location_ids = []

        for frame in reversed(stacktrace["stacktrace"]):
            location_ids.append(get_location(frame).id)

        sample.location_id.extend(location_ids)
        sample.label.extend(labels)

        samples.append(sample)

    pb_profile.sample.extend(samples)
    pb_profile.string_table.extend(str_table.keys())
    pb_profile.function.extend(list(functions_table.values()))
    pb_profile.location.extend(list(locations_table.values()))

    return gzip.compress(pb_profile.SerializeToString())


def _extract_log_processor_thread_id(processor):
    if hasattr(processor, "_worker_thread"):
        # pylint: disable-next=protected-access
        worker_thread = processor._worker_thread

        if isinstance(worker_thread, threading.Thread):
            return worker_thread.ident

    return None


def _get_ignored_thread_ids(batch_processor, include_internal_stacks=False):
    if include_internal_stacks:
        return []

    ignored_ids = [threading.get_ident()]

    log_processor_thread_id = _extract_log_processor_thread_id(batch_processor)

    if log_processor_thread_id:
        ignored_ids.append(log_processor_thread_id)

    return ignored_ids


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
            "stacktrace": stacktrace_frames,
            "tid": thread_id,
        }
        stacktraces.append(stacktrace)
    return stacktraces


def _to_log_record(
    stacktraces, timestamp_unix_nanos, call_stack_interval_millis, resource
):
    encoded_profile = base64.b64encode(
        _encode_cpu_profile(stacktraces, timestamp_unix_nanos, call_stack_interval_millis)
    ).decode()

    return LogRecord(
        timestamp=timestamp_unix_nanos,
        trace_id=0,
        span_id=0,
        trace_flags=TraceFlags(0x01),
        severity_number=SeverityNumber.UNSPECIFIED,
        body=encoded_profile,
        resource=resource,
        attributes={
            "profiling.data.format": "pprof-gzip-base64",
            "profiling.data.type": "cpu",
            "com.splunk.sourcetype": "otel.profiling",
            "profiling.data.total.frame.count": len(stacktraces),
        },
    )


def _profiler_loop(profiler: Profiler):
    options = profiler.options
    call_stack_interval_millis = options.call_stack_interval_millis

    ignored_thread_ids = _get_ignored_thread_ids(
        profiler.batch_processor, include_internal_stacks=options.include_internal_stacks
    )

    profiling_logger = profiler.logger_provider.get_logger("otel.profiling", "0.1.0")

    call_stack_interval_seconds = call_stack_interval_millis / 1e3
    # In case the processing takes more than the given interval, default to the smallest allowed interval
    min_call_stack_interval_seconds = 1 / 1e3
    while profiler.running:
        time_begin = time.time()
        timestamp = int(time_begin * 1e9)

        stacktraces = _collect_stacktraces(ignored_thread_ids)

        log_record = _to_log_record(
            stacktraces, timestamp, call_stack_interval_millis, options.resource
        )

        profiling_logger.emit(log_record)

        processing_time = time.time() - time_begin
        wait_for = max(
            call_stack_interval_seconds - processing_time, min_call_stack_interval_seconds
        )

        with profiler.condition:
            profiler.condition.wait(wait_for)

    # Hack around batch log processor getting stuck on application exits when the profiling endpoint is not reachable
    # Could be related: https://github.com/open-telemetry/opentelemetry-python/issues/2284
    # pylint: disable-next=protected-access
    profiler.exporter._shutdown = True
    profiler.logger_provider.shutdown()
    with profiler.condition:
        profiler.condition.notify_all()


def _wrapped_context_attach(wrapped, _instance, args, kwargs):
    token = wrapped(*args, **kwargs)

    maybe_context = args[0] if args else None

    if maybe_context:
        span = maybe_context.get(_SPAN_KEY)

        if span:
            thread_id = threading.get_ident()
            _profiler.thread_states[thread_id] = (
                span.context.trace_id,
                span.context.span_id,
            )

    return token


def _wrapped_context_detach(wrapped, _instance, args, kwargs):
    token = args[0] if args else None

    if token:
        prev = token.old_value
        thread_id = threading.get_ident()
        if isinstance(prev, Context):
            span = prev.get(_SPAN_KEY)

            if span:
                _profiler.thread_states[thread_id] = (
                    span.context.trace_id,
                    span.context.span_id,
                )
            else:
                _profiler.thread_states[thread_id] = None
        else:
            _profiler.thread_states[thread_id] = None
    return wrapped(*args, **kwargs)


def _start_profiler_thread():
    profiler_thread = threading.Thread(
        name="splunk-otel-profiler", target=_profiler_loop, args=[_profiler], daemon=True
    )
    profiler_thread.start()


def _force_flush():
    if _profiler.logger_provider:
        _profiler.logger_provider.force_flush()


def _start_profiling(options):
    if _profiler.running:
        logger.warning("profiler already running")
        return

    _profiler.options = options
    _profiler.logger_provider = LoggerProvider(resource=options.resource)
    _profiler.exporter = OTLPLogExporter(options.endpoint)
    _profiler.batch_processor = BatchLogRecordProcessor(_profiler.exporter)
    _profiler.logger_provider.add_log_record_processor(_profiler.batch_processor)
    _profiler.running = True

    logger.debug(
        "starting profiling call_stack_interval_millis=%s endpoint=%s",
        options.call_stack_interval_millis,
        options.endpoint,
    )
    wrapt.wrap_function_wrapper(opentelemetry.context, "attach", _wrapped_context_attach)
    wrapt.wrap_function_wrapper(opentelemetry.context, "detach", _wrapped_context_detach)

    # Windows does not have register_at_fork
    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=_start_profiler_thread)
    atexit.register(stop_profiling)

    _start_profiler_thread()


def start_profiling(
    service_name: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    endpoint: Optional[str] = None,
    call_stack_interval_millis: Optional[int] = None,
):
    # pylint: disable-next=protected-access
    resource = splunk_otel.options._Options._get_resource(
        service_name, resource_attributes
    )
    options = _Options(resource, endpoint, call_stack_interval_millis)
    _start_profiling(options)


def stop_profiling():
    if not _profiler.running:
        return

    _profiler.running = False
    with _profiler.condition:
        # Wake up the profiler thread
        _profiler.condition.notify_all()
        # Wait for the profiler thread to exit
        _profiler.condition.wait()

    unwrap(opentelemetry.context, "attach")
    unwrap(opentelemetry.context, "detach")
