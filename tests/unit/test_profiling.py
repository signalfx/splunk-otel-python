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
import random
import threading
import time
import unittest
from unittest.mock import patch

from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs.export import LogExportResult
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from splunk_otel.profiling import _force_flush, profile_pb2, start_profiling


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


class TestProfiling(unittest.TestCase):
    def setUp(self):
        self.span_id = None
        self.trace_id = None
        self.export_patcher = patch.object(OTLPLogExporter, "export")
        self.export_mock = self.export_patcher.start()
        self.export_mock.return_value = LogExportResult.SUCCESS

    def tearDown(self):
        self.export_patcher.stop()

    def _assert_scope(self, scope):
        self.assertEqual(scope.name, "otel.profiling")
        self.assertEqual(scope.version, "0.1.0")

    def _assert_log_record(self, log_record):
        self.assertTrue(int(time.time() * 1e9) - log_record.timestamp <= 2e9)

        self.assertEqual(log_record.trace_id, 0)
        self.assertEqual(log_record.span_id, 0)
        # Attributes are of type BoundedAttributes, get the underlying dict
        self.assertDictEqual(
            log_record.attributes.copy(),
            {
                "profiling.data.format": "pprof-gzip-base64",
                "profiling.data.type": "cpu",
                "com.splunk.sourcetype": "otel.profiling",
            },
        )

        resource = log_record.resource.attributes

        self.assertEqual(resource["foo"], "bar")
        self.assertEqual(resource["telemetry.sdk.language"], "python")
        self.assertEqual(resource["service.name"], "prof-export-test")

        body = log_record.body
        pprof_gzipped = base64.b64decode(body)
        pprof = gzip.decompress(pprof_gzipped)
        profile = profile_pb2.Profile()
        profile.ParseFromString(pprof)

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
                location = locations[location_id]
                function = functions[location.line[0].function_id]
                function_name = strings[function.name]
                file_name = strings[function.filename]
                self.assertGreater(len(file_name), 0)

                if function_name == "do_work":
                    span_id = int(strings[find_label(sample, "span_id", strings).str], 16)
                    trace_id = int(
                        strings[find_label(sample, "trace_id", strings).str], 16
                    )
                    self.assertEqual(span_id, self.span_id)
                    self.assertEqual(trace_id, self.trace_id)
                    return True

        return False

    def test_profiling_export(self):
        provider = TracerProvider()
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace_api.set_tracer_provider(provider)
        tracer = trace_api.get_tracer("tests.tracer")

        start_profiling(
            service_name="prof-export-test",
            resource_attributes={"foo": "bar"},
            call_stack_interval=100,
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
