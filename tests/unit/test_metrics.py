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

from opentelemetry.metrics import NoOpMeterProvider, get_meter_provider
from opentelemetry.sdk.metrics import MeterProvider

from splunk_otel.metrics import _configure_metrics, start_metrics
from splunk_otel.version import __version__

# pylint: disable=protected-access


class TestMetrics(TestCase):
    @mock.patch.dict(
        os.environ,
        {"OTEL_METRICS_ENABLED": "False"},
    )
    def test_metrics_disabled(self):
        meter_provider = start_metrics()
        self.assertNotIsInstance(meter_provider, MeterProvider)

    @mock.patch.dict(
        os.environ,
        {"OTEL_METRICS_ENABLED": "True"},
    )
    def test_metrics_enabled(self):
        meter_provider = start_metrics()
        self.assertIsInstance(meter_provider, MeterProvider)
        meter_provider.shutdown(1)

    def test_configure_metrics(self):
        meter_provider = _configure_metrics()
        self.assertIsInstance(meter_provider, MeterProvider)

    def test_configure_metrics_global_provider(self):
        global_meter_provider = get_meter_provider()
        self.assertNotIsInstance(global_meter_provider, NoOpMeterProvider)
        self.assertIsInstance(global_meter_provider, MeterProvider)
