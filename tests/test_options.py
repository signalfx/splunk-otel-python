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

from opentelemetry.sdk.resources import Resource

from splunk_otel.options import Options


class TestOptions(TestCase):
    def test_default_service_name(self):
        options = Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["service.name"], "unnamed-python-service"
        )

    def test_service_name_from_kwargs(self):
        options = Options(
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
        options = Options()
        self.assertIsInstance(options.resource, Resource)
        self.assertEqual(
            options.resource.attributes["service.name"], "test service name from env"
        )

    @mock.patch.dict(
        os.environ,
        {"OTEL_SERVICE_NAME": "service name from otel service name env"},
    )
    def test_service_name_from_env_service_name(self):
        options = Options()
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
        Options()
        self.assertEqual(
            os.environ["OTEL_SERVICE_NAME"], os.environ["SPLUNK_SERVICE_NAME"]
        )
        del os.environ["OTEL_SERVICE_NAME"]
