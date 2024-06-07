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

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from splunk_otel.options import _Options
from splunk_otel.version import __version__

# pylint: disable=protected-access


class TestOptions(TestCase):
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
        self.assertTrue(("x-sf-token", "12345") in exporter._headers)

    def test_telemetry_attributes(self):
        options = _Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["splunk.distro.version"],
            __version__,
        )
