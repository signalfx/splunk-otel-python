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

import base64
import gzip
import logging
import os
import sys
import threading
import time
import traceback
from collections import OrderedDict
from typing import Dict, Optional, Union

import wrapt
from opentelemetry._logs import SeverityNumber
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LogData, LogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import TraceFlags
from opentelemetry.trace.propagation import _SPAN_KEY

import splunk_otel
from splunk_otel.profiling import profile_pb2
from splunk_otel.profiling.options import _Options
from splunk_otel.version import __version__

logger = logging.getLogger(__name__)


class Profiler:
    def __init__(self):
        self.running = False
        self.thread_states = {}
        self.batch_processor = None


profiler = Profiler()


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


def _encode_cpu_profile(stacktraces, interval):
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
        timestamp_label.num = int(stacktrace["timestamp"] / 1e6)

        thread_id_label = profile_pb2.Label()
        thread_id_label.key = thread_id_key
        thread_id_label.num = thread_id

        labels = [timestamp_label, event_period_label, thread_id_label]

        trace_context = profiler.thread_states.get(thread_id)
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


def _profiler_loop(options: _Options):
    interval = options.call_stack_interval

    exporter = OTLPLogExporter(options.endpoint)
    # pylint: disable-next=global-statement
    profiler.batch_processor = BatchLogRecordProcessor(exporter)

    while True:
        profiling_stacktraces = []
        frames = sys._current_frames()
        timestamp = int(time.time() * 1e9)

        for thread_id, frame in frames.items():
            prof_stacktrace_frames = []
            # TODO: This is potentially really slow due to code line lookups in the file
            stack = traceback.extract_stack(frame)
            for sf in stack:
                prof_stacktrace_frames.append((sf.filename, sf.name, sf.lineno))
            prof_stacktrace = {
                "timestamp": timestamp,
                "stacktrace": prof_stacktrace_frames,
                "tid": thread_id,
            }
            profiling_stacktraces.append(prof_stacktrace)

        encoded_profile = base64.b64encode(
            _encode_cpu_profile(profiling_stacktraces, interval)
        ).decode()
        log_data = LogData(
            log_record=LogRecord(
                timestamp=timestamp,
                trace_id=0,
                span_id=0,
                trace_flags=TraceFlags(0x01),
                severity_number=SeverityNumber.UNSPECIFIED,
                body=encoded_profile,
                resource=options.resource,
                attributes={
                    "profiling.data.format": "pprof-gzip-base64",
                    "profiling.data.type": "cpu",
                    "com.splunk.sourcetype": "otel.profiling",
                    "profiling.data.total.frame.count": len(profiling_stacktraces)
                },
            ),
            instrumentation_scope=InstrumentationScope("otel.profiling", "0.1.0"),
        )
        profiler.batch_processor.emit(log_data)
        time.sleep(interval / 1e3)


def _wrapped_context_attach(wrapped, _instance, args, kwargs):
    token = wrapped(*args, **kwargs)

    maybe_context = args[0] if args else None

    if maybe_context:
        span = maybe_context.get(_SPAN_KEY)

        if span:
            thread_id = threading.get_ident()
            profiler.thread_states[thread_id] = (
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
                profiler.thread_states[thread_id] = (
                    span.context.trace_id,
                    span.context.span_id,
                )
            else:
                profiler.thread_states[thread_id] = None
        else:
            profiler.thread_states[thread_id] = None
    return wrapped(*args, **kwargs)


def _force_flush():
    if profiler.batch_processor:
        profiler.batch_processor.force_flush()


def _start_profiling(options):
    if profiler.running:
        logger.warning("profiler already running")
        return

    profiler.running = True
    logger.debug(
        "starting profiling call_stack_interval=%s endpoint=%s",
        options.call_stack_interval,
        options.endpoint,
    )
    wrapt.wrap_function_wrapper(
        "opentelemetry.context", "attach", _wrapped_context_attach
    )
    wrapt.wrap_function_wrapper(
        "opentelemetry.context", "detach", _wrapped_context_detach
    )

    profiler_thread = threading.Thread(
        name="splunk-otel-profiler", target=_profiler_loop, args=[options], daemon=True
    )
    profiler_thread.start()


def start_profiling(
    service_name: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    endpoint: Optional[str] = None,
    call_stack_interval: Optional[int] = None,
):
    # pylint: disable-next=protected-access
    resource = splunk_otel.options._Options._get_resource(
        service_name, resource_attributes
    )
    options = _Options(resource, endpoint, call_stack_interval)
    _start_profiling(options)
