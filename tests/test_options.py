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

import logging
import os
from functools import partial
from unittest import TestCase, mock

from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from splunk_otel.options import Options, _splunk_env_var
from splunk_otel.symbols import DEFAULT_JAEGER_ENDPOINT, DEFAULT_MAX_ATTR_LENGTH


class TestOptions(TestCase):
    @mock.patch.dict(
        os.environ, {"SPLK_OLD_VAR": "OLD_VALUE", "SPLUNK_NEW_VAR": "NEW_VALUE"}
    )
    def test_from_env(self):
        self.assertIsNone(_splunk_env_var("TEST_VAR1"))
        self.assertEqual(_splunk_env_var("TEST_VAR1", "default value"), "default value")

        with self.assertLogs(level=logging.WARNING) as warning:
            self.assertEqual(_splunk_env_var("OLD_VAR"), "OLD_VALUE")
            self.assertIn(
                "SPLK_OLD_VAR is deprecated and will be removed soon. Please use SPLUNK_OLD_VAR instead",
                warning.output[0],
            )
        self.assertEqual(_splunk_env_var("NEW_VAR"), "NEW_VALUE")

    def test_default_service_name(self):
        options = Options()
        self.assertIsInstance(options.resource_attributes, dict)
        self.assertEqual(
            options.resource_attributes["service.name"], "unnamed-python-service"
        )

    def test_service_name_from_kwargs(self):
        options = Options(
            resource_attributes={"service.name": "test service name from kwargs"}
        )
        self.assertIsInstance(options.resource_attributes, dict)
        self.assertEqual(
            options.resource_attributes["service.name"], "test service name from kwargs"
        )

    @mock.patch.dict(
        os.environ,
        {"OTEL_RESOURCE_ATTRIBUTES": "service.name=test service name from env"},
    )
    def test_service_name_from_env(self):
        options = Options()
        self.assertIsInstance(options.resource_attributes, dict)
        self.assertEqual(
            options.resource_attributes["service.name"], "test service name from env"
        )

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": ""})
    def test_exporters_default(self):
        options = Options()
        self.assertEqual(len(options.exporter_factories), 1)
        self.assertEqual(options.exporter_factories[0], OTLPSpanExporter)

    def test_exporters_from_kwargs(self):
        options = Options(exporter_factories=[OTLPSpanExporter, ConsoleSpanExporter])
        self.assertEqual(len(options.exporter_factories), 2)
        self.assertIn(OTLPSpanExporter, options.exporter_factories)
        self.assertIn(ConsoleSpanExporter, options.exporter_factories)

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "otlp,console_span"})
    def test_exporters_from_env(self):
        options = Options()
        self.assertEqual(len(options.exporter_factories), 2)
        self.assertIn(OTLPSpanExporter, options.exporter_factories)
        self.assertIn(ConsoleSpanExporter, options.exporter_factories)

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "jaeger-thrift-splunk"})
    def test_exporters_jaeger_defaults(self):
        options = Options()
        self.assertEqual(len(options.exporter_factories), 1)
        self.assertIsInstance(options.exporter_factories[0], partial)
        jaeger_partial = options.exporter_factories[0]
        self.assertEqual(jaeger_partial.func, JaegerExporter)
        self.assertEqual(
            jaeger_partial.keywords,
            {
                "max_tag_value_length": DEFAULT_MAX_ATTR_LENGTH,
                "collector_endpoint": DEFAULT_JAEGER_ENDPOINT,
            },
        )

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
        options = Options()
        self.assertEqual(len(options.exporter_factories), 1)
        self.assertIsInstance(options.exporter_factories[0], partial)
        jaeger_partial = options.exporter_factories[0]
        self.assertEqual(jaeger_partial.func, JaegerExporter)
        self.assertEqual(
            jaeger_partial.keywords,
            {
                "max_tag_value_length": 10,
                "collector_endpoint": "localhost:1234",
                "username": "auth",
                "password": "12345",
            },
        )

    @mock.patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "otlp"})
    def test_exporters_otlp_defaults(self):
        options = Options()
        self.assertEqual(len(options.exporter_factories), 1)
        self.assertEqual(options.exporter_factories[0], OTLPSpanExporter)

    @mock.patch.dict(
        os.environ,
        {
            "OTEL_TRACES_EXPORTER": "otlp",
            "SPLUNK_MAX_ATTR_LENGTH": "10",
            "SPLUNK_ACCESS_TOKEN": "12345",
        },
    )
    def test_exporters_otlp_custom(self):
        options = Options()
        self.assertEqual(len(options.exporter_factories), 1)
        self.assertIsInstance(options.exporter_factories[0], partial)
        otlp_partial = options.exporter_factories[0]
        self.assertEqual(otlp_partial.func, OTLPSpanExporter)
        self.assertEqual(
            otlp_partial.keywords,
            {
                "headers": (
                    (
                        "x-sf-token",
                        "12345",
                    ),
                ),
            },
        )
