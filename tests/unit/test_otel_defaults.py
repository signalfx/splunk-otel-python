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

import unittest
from os import environ

from opentelemetry.sdk.trace import TracerProvider

from splunk_otel.defaults import _OTEL_PYTHON_LOG_CORRELATION
from splunk_otel.options import _Options


class TestOtelDefaults(unittest.TestCase):
    # pylint: disable=protected-access,import-outside-toplevel

    def test_default_limits(self):
        # instantiating _Options() sets default env vars
        _Options()
        limits = TracerProvider()._span_limits
        self.assertIsNone(limits.max_attributes)
        self.assertIsNone(limits.max_events)
        self.assertEqual(limits.max_links, 1000)

    def test_otel_log_correlation_enabled(self):
        self.assertTrue(environ[_OTEL_PYTHON_LOG_CORRELATION])
