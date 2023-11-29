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
import os
import random
import threading
import time
import unittest
from unittest import mock

from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs.export import LogExportResult
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from splunk_otel.profiling import (
    _force_flush,
    profile_pb2,
    start_profiling,
    stop_profiling,
)


def do_work(time_ms):
    now = time.time()
    target = now + time_ms / 1000.0

    total = 0.0
    while now < target:
        value = random.random()
        for _ in range(0, 10000):
            value = value + random.random()

        total = total + value

        now = time.time()
        time.sleep(0.01)

    return total


def find_label(sample, name, strings):
    for label in sample.label:
        if strings[label.key] == name:
            return label
    return None


def log_record_to_profile(log_record):
    body = log_record.body
    pprof_gzipped = base64.b64decode(body)
    pprof = gzip.decompress(pprof_gzipped)
    profile = profile_pb2.Profile()
    profile.ParseFromString(pprof)
    return profile


class TestProfiling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tracing is set up to correlate active spans with stacktraces.
        # When the profiler takes a sample while a span is active, it stores the trace context into the stacktrace.
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace_api.set_tracer_provider(provider)

    def setUp(self):
        self.span_id = None
        self.trace_id = None
        self.export_patcher = mock.patch.object(OTLPLogExporter, "export")
        self.export_mock = self.export_patcher.start()
        self.export_mock.return_value = LogExportResult.SUCCESS

    def tearDown(self):
        self.export_patcher.stop()
        stop_profiling()

    def profile_capture_thread_ids(self):
        start_profiling(
            service_name="prof-thread-filter",
            call_stack_interval_millis=10,
        )

        do_work(100)
        stop_profiling()

        args = self.export_mock.call_args
        (log_datas,) = args[0]
        self.assertGreaterEqual(len(log_datas), 5)

        thread_ids = set()
        for log_data in log_datas:
            profile = log_record_to_profile(log_data.log_record)

            strings = profile.string_table

            for sample in profile.sample:
                thread_ids.add(find_label(sample, "thread.id", strings).num)

        return thread_ids

    def _assert_scope(self, scope):
        self.assertEqual(scope.name, "otel.profiling")
        self.assertEqual(scope.version, "0.1.0")

    def _assert_log_record(self, log_record):
        self.assertTrue(int(time.time() * 1e9) - log_record.timestamp <= 2e9)

        self.assertEqual(log_record.trace_id, 0)
        self.assertEqual(log_record.span_id, 0)
        # Attributes are of type BoundedAttributes, get the underlying dict
        attributes = log_record.attributes.copy()

        self.assertEqual(attributes["profiling.data.format"], "pprof-gzip-base64")
        self.assertEqual(attributes["profiling.data.type"], "cpu")
        self.assertEqual(attributes["com.splunk.sourcetype"], "otel.profiling")
        # We should at least have the main thread
        self.assertGreaterEqual(attributes["profiling.data.total.frame.count"], 1)

        resource = log_record.resource.attributes

        self.assertEqual(resource["foo"], "bar")
        self.assertEqual(resource["telemetry.sdk.language"], "python")
        self.assertEqual(resource["service.name"], "prof-export-test")

        profile = log_record_to_profile(log_record)

        strings = profile.string_table
        locations = profile.location
        functions = profile.function

        main_thread_samples = []

        for sample in profile.sample:
            thread_id = find_label(sample, "thread.id", strings).num
            period = find_label(sample, "source.event.period", strings).num
            self.assertEqual(period, 100)

            # Only care for the main thread which is running our busy function
            if thread_id == threading.get_ident():
                main_thread_samples.append(sample)

        for sample in main_thread_samples:
            for location_id in sample.location_id:
                location = locations[location_id - 1]
                function = functions[location.line[0].function_id - 1]
                function_name = strings[function.name]
                file_name = strings[function.filename]
                self.assertGreater(len(file_name), 0)

                if function_name == "do_work":
                    span_id_str = strings[find_label(sample, "span_id", strings).str]
                    trace_id_str = strings[find_label(sample, "trace_id", strings).str]
                    self.assertFalse(span_id_str.startswith("0x"))
                    self.assertFalse(trace_id_str.startswith("0x"))
                    span_id = int(span_id_str, 16)
                    trace_id = int(trace_id_str, 16)
                    self.assertEqual(span_id, self.span_id)
                    self.assertEqual(trace_id, self.trace_id)
                    return True

        return False

    def test_profiling_export(self):
        tracer = trace_api.get_tracer("tests.tracer")

        start_profiling(
            service_name="prof-export-test",
            resource_attributes={"foo": "bar"},
            call_stack_interval_millis=100,
        )

        with tracer.start_as_current_span("add-some-numbers") as span:
            span_ctx = span.get_span_context()
            self.span_id = span_ctx.span_id
            self.trace_id = span_ctx.trace_id
            do_work(550)

        _force_flush()

        self.export_mock.assert_called()

        args = self.export_mock.call_args
        (log_datas,) = args[0]

        # We expect at least 5 profiling cycles during a 550ms run with call_stack_interval=100
        self.assertGreaterEqual(len(log_datas), 5)

        busy_function_profiled = False
        for log_data in log_datas:
            log_record = log_data.log_record
            self._assert_scope(log_data.instrumentation_scope)
            if self._assert_log_record(log_record):
                busy_function_profiled = True

        self.assertTrue(busy_function_profiled)

    def test_include_internal_threads(self):
        with_internal_stacks_thread_ids = set()
        with mock.patch.dict(
            os.environ, {"SPLUNK_PROFILER_INCLUDE_INTERNAL_STACKS": "true"}, clear=True
        ):
            with_internal_stacks_thread_ids = self.profile_capture_thread_ids()

        without_internal_stacks_thread_ids = set()
        with mock.patch.dict(
            os.environ, {"SPLUNK_PROFILER_INCLUDE_INTERNAL_STACKS": "false"}, clear=True
        ):
            without_internal_stacks_thread_ids = self.profile_capture_thread_ids()

        # Internally the profiler should use 2 threads: the sampler thread and export thread.
        count_diff = len(with_internal_stacks_thread_ids) - len(
            without_internal_stacks_thread_ids
        )
        self.assertEqual(count_diff, 2)
