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

import os
from unittest import TestCase, mock

from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from splunk_otel.options import _Options
from splunk_otel.symbols import _DEFAULT_JAEGER_ENDPOINT, _DEFAULT_MAX_ATTR_LENGTH
from splunk_otel.version import __version__

# pylint: disable=protected-access


class TestOptions(TestCase):
    def test_default_service_name(self):
        options = _Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["service.name"], "unnamed-python-service"
        )

    def test_service_name_from_kwargs(self):
        options = _Options(
            resource_attributes={"service.name": "test service name from kwargs"}
        )
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["service.name"], "test service name from kwargs"
        )

    @mock.patch.dict(
        os.environ,
        {"OTEL_RESOURCE_ATTRIBUTES": "service.name=test service name from env"},
    )
    def test_service_name_from_env_resource_attrs(self):
        options = _Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["service.name"], "test service name from env"
        )

    @mock.patch.dict(
        os.environ,
        {"OTEL_SERVICE_NAME": "service name from otel service name env"},
    )
    def test_service_name_from_env_service_name(self):
        options = _Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["service.name"],
            "service name from otel service name env",
        )

    @mock.patch.dict(
        os.environ,
        {"SPLUNK_SERVICE_NAME": "service name from splunk env"},
    )
    def test_service_name_backward_compatibility(self):
        self.assertNotIn("OTEL_SERVICE_NAME", os.environ)
        _Options()
        self.assertEqual(
            os.environ["OTEL_SERVICE_NAME"], os.environ["SPLUNK_SERVICE_NAME"]
        )
        del os.environ["OTEL_SERVICE_NAME"]

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": ""})
    def test_exporters_default(self):
        options = _Options()
        self.assertEqual(len(options.span_exporter_factories), 1)
        otlp = options.span_exporter_factories[0](options)
        self.assertIsInstance(otlp, OTLPSpanExporter)

    def test_exporters_from_kwargs_classes(self):
        options = _Options(
            span_exporter_factories=[
                lambda opts: OTLPSpanExporter(),
                lambda opts: ConsoleSpanExporter(),
            ]
        )
        self.assertEqual(len(options.span_exporter_factories), 2)
        self.assertIsInstance(
            options.span_exporter_factories[0](options), OTLPSpanExporter
        )
        self.assertIsInstance(
            options.span_exporter_factories[1](options), ConsoleSpanExporter
        )

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "otlp,console_span"})
    def test_exporters_from_env(self):
        options = _Options()
        self.assertEqual(len(options.span_exporter_factories), 2)

        otlp = options.span_exporter_factories[0](options)
        self.assertIsInstance(otlp, OTLPSpanExporter)
        self.assertEqual(
            otlp._headers,
            (
                (
                    "x-sf-token",
                    None,
                ),
            ),
        )

        self.assertIsInstance(
            options.span_exporter_factories[1](options), ConsoleSpanExporter
        )

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "jaeger-thrift-splunk"})
    def test_exporters_jaeger_defaults(self):
        options = _Options()
        self.assertEqual(len(options.span_exporter_factories), 1)
        factory = options.span_exporter_factories[0]
        exporter = factory(options)
        self.assertIsInstance(exporter, JaegerExporter)
        self.assertEqual(exporter.collector_endpoint, _DEFAULT_JAEGER_ENDPOINT)
        self.assertEqual(exporter._max_tag_value_length, _DEFAULT_MAX_ATTR_LENGTH)

    @mock.patch.dict(
        os.environ,
        {
            "OTEL_TRACES_EXPORTER": "jaeger-thrift-splunk",
            "OTEL_EXPORTER_JAEGER_ENDPOINT": "localhost:1234",
            "SPLUNK_MAX_ATTR_LENGTH": "10",
            "SPLUNK_ACCESS_TOKEN": "12345",
        },
    )
    def test_exporters_jaeger_custom(self):
        options = _Options()
        self.assertEqual(len(options.span_exporter_factories), 1)
        factory = options.span_exporter_factories[0]
        exporter = factory(options)
        self.assertIsInstance(exporter, JaegerExporter)
        self.assertEqual(exporter.collector_endpoint, "localhost:1234")
        self.assertEqual(exporter._max_tag_value_length, 10)
        self.assertEqual(exporter.username, "auth")
        self.assertEqual(exporter.password, "12345")

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "otlp"})
    def test_exporters_otlp_defaults(self):
        options = _Options()
        self.assertEqual(len(options.span_exporter_factories), 1)
        factory = options.span_exporter_factories[0]
        exporter = factory(options)
        self.assertIsInstance(exporter, OTLPSpanExporter)

    @mock.patch.dict(
        os.environ,
        {
            "OTEL_TRACES_EXPORTER": "otlp",
            "SPLUNK_MAX_ATTR_LENGTH": "10",
            "SPLUNK_ACCESS_TOKEN": "12345",
        },
    )
    def test_exporters_otlp_custom(self):
        options = _Options()
        self.assertEqual(len(options.span_exporter_factories), 1)

        factory = options.span_exporter_factories[0]
        exporter = factory(options)
        self.assertIsInstance(exporter, OTLPSpanExporter)
        self.assertEqual(
            exporter._headers,
            (
                (
                    "x-sf-token",
                    "12345",
                ),
            ),
        )

    def test_telemetry_attributes(self):
        options = _Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["splunk.distro.version"],
            __version__,
        )
