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
from typing import Dict, Optional
from unittest import TestCase

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.propagators import get_global_response_propagator
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from splunk_otel.env import _EnvVarsABC
from splunk_otel.propagators import _ServerTimingResponsePropagator
from splunk_otel.tracing import _do_start_tracing


class TestTracing(TestCase):
    def test_do_start_with_tracing_disabled(self):
        env = _FakeEnvVars({"OTEL_TRACE_ENABLED": False})
        res = _do_start_tracing(env)
        self.assertIsNone(res)

    def test_do_start_tracing_with_defaults(self):
        env = _FakeEnvVars()
        tracer_provider = _do_start_tracing(env)
        self.assertIsNotNone(tracer_provider)
        env_vars = env.get_env_vars_written()
        expected_written = {
            "OTEL_ATTRIBUTE_COUNT_LIMIT": "",
            "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "",
            "OTEL_SPAN_EVENT_COUNT_LIMIT": "",
            "OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT": "",
            "OTEL_LINK_ATTRIBUTE_COUNT_LIMIT": "",
            "OTEL_SPAN_LINK_COUNT_LIMIT": "1000",
            "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT": "12000",
        }
        self.assertDictEqual(expected_written, env_vars)
        read = env.get_env_vars_read()
        expected_read = [
            "OTEL_TRACE_ENABLED",
            "SPLUNK_ACCESS_TOKEN",
            "SPLUNK_TRACE_RESPONSE_HEADER_ENABLED",
            "OTEL_TRACES_EXPORTER",
        ]
        self.assertListEqual(expected_read, read)
        self.assertIsInstance(
            get_global_response_propagator(), _ServerTimingResponsePropagator
        )

        expected_attrs = {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.19.0",
            "telemetry.auto.version": "0.40b0",
            "splunk.distro.version": "1.12.0",
            "service.name": "unnamed-python-service",
        }
        self.assertDictEqual(expected_attrs, dict(tracer_provider.resource.attributes))
        # pylint:disable=protected-access
        batch_span_processor = tracer_provider._active_span_processor._span_processors[0]
        self.assertIsInstance(batch_span_processor.span_exporter, OTLPSpanExporter)

    def test_do_start_tracing_with_access_token(self):
        env = _FakeEnvVars({"SPLUNK_ACCESS_TOKEN": "abc123"})
        tracer_provider = _do_start_tracing(env)
        # pylint:disable=protected-access
        otlp_span_exporter = tracer_provider._active_span_processor._span_processors[0].span_exporter
        self.assertIn(("x-sf-token", "abc123"), otlp_span_exporter._headers)

    def test_do_start_tracing_with_svc_name(self):
        tracer_provider = _do_start_tracing(_FakeEnvVars(), service_name="my.service")
        expected_attrs = {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.19.0",
            "telemetry.auto.version": "0.40b0",
            "splunk.distro.version": "1.12.0",
            "service.name": "my.service",
        }
        self.assertDictEqual(expected_attrs, dict(tracer_provider.resource.attributes))

    def test_do_start_tracing_with_response_header_disabled(self):
        _do_start_tracing(_FakeEnvVars(), trace_response_header_enabled=False)
        self.assertIsNone(get_global_response_propagator())

    def test_do_start_tracing_with_span_exporter_factory(self):
        tracer_provider = _do_start_tracing(
            _FakeEnvVars(),
            span_exporter_factories=[lambda options: InMemorySpanExporter()],
        )
        # pylint:disable=protected-access
        exporter = tracer_provider._active_span_processor._span_processors[
            0
        ].span_exporter
        self.assertIsInstance(exporter, InMemorySpanExporter)

    def test_do_start_tracing_with_resource_attrs(self):
        tracer_provider = _do_start_tracing(
            _FakeEnvVars(), resource_attributes={"my.attr": 42}
        )
        expected_attrs = {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.19.0",
            "telemetry.auto.version": "0.40b0",
            "splunk.distro.version": "1.12.0",
            "service.name": "unnamed-python-service",
            "my.attr": 42,
        }
        self.assertDictEqual(expected_attrs, dict(tracer_provider.resource.attributes))

    def test_jaeger_exporter_defaults(self):
        env = _FakeEnvVars({"OTEL_TRACES_EXPORTER": "jaeger-thrift-splunk"})
        tracer_provider = _do_start_tracing(env)
        exporter = tracer_provider._active_span_processor._span_processors[0].span_exporter
        self.assertIsInstance(exporter, JaegerExporter)
        self.assertEqual("http://localhost:9080/v1/trace", exporter.collector_endpoint)

    def test_jaeger_exporter_explicit_endpoint(self):
        endpt = "http://example.com:4200"
        env = _FakeEnvVars({
            "OTEL_TRACES_EXPORTER": "jaeger-thrift-splunk",
            "OTEL_EXPORTER_JAEGER_ENDPOINT": endpt,
        })
        tracer_provider = _do_start_tracing(env)
        exporter = tracer_provider._active_span_processor._span_processors[0].span_exporter
        self.assertIsInstance(exporter, JaegerExporter)
        self.assertEqual(endpt, exporter.collector_endpoint)

    def test_jaeger_thrift_defaults(self):
        env = _FakeEnvVars({
            "OTEL_TRACES_EXPORTER": "jaeger_thrift",
        })
        tracer_provider = _do_start_tracing(env)
        exporter = tracer_provider._active_span_processor._span_processors[0].span_exporter
        self.assertIsInstance(exporter, JaegerExporter)

    def test_jaeger_thrift_with_access_token(self):
        env = _FakeEnvVars({
            "OTEL_TRACES_EXPORTER": "jaeger_thrift",
            "SPLUNK_ACCESS_TOKEN": "abc123",
        })
        tracer_provider = _do_start_tracing(env)
        exporter = tracer_provider._active_span_processor._span_processors[0].span_exporter
        self.assertIsInstance(exporter, JaegerExporter)
        self.assertEqual("auth", exporter.username)
        self.assertEqual("abc123", exporter.password)

    def test_console_exporter(self):
        env = _FakeEnvVars({
            "OTEL_TRACES_EXPORTER": "console",
        })
        tracer_provider = _do_start_tracing(env)
        exporter = tracer_provider._active_span_processor._span_processors[0].span_exporter
        self.assertIsInstance(exporter, ConsoleSpanExporter)

    def test_bad_exporter_name(self):
        env = _FakeEnvVars({
            "OTEL_TRACES_EXPORTER": "foo",
        })
        with self.assertRaises(ValueError) as context:
            _do_start_tracing(env)
        self.assertEqual(
            str(context.exception),
            'exporter "foo (foo)" not found. please make sure the relevant exporter package is installed.',
        )


# A test/fake implementation for accessing environment variables. Just uses a dictionary instead of env vars.
class _FakeEnvVars(_EnvVarsABC):
    def __init__(self, starting_env=None):
        self._env = starting_env or {}
        self._written = {}
        self._read = []

    def get(self, name: str, default: Optional[any] = None) -> any:
        self._read.append(name)
        out = self._env.get(name)
        return default if out is None else out

    def set_all_unset(self, pairs: Dict):
        for name, value in pairs.items():
            if name not in self._written:
                self.set(name, value)

    def set(self, name: str, value: str):
        self._written[name] = value
        self._env[value] = value

    def get_env_vars_written(self):
        return self._written

    def get_env_vars_read(self):
        return self._read
