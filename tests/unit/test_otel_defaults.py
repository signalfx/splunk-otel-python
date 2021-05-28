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
from importlib import reload

from opentelemetry.sdk import trace


class TestOtelDefaults(unittest.TestCase):
    # pylint: disable=protected-access,import-outside-toplevel

    def test_otel_span_link_count_limit(self):
        self.assertEqual(trace._SPAN_LINK_COUNT_LIMIT, 128)
        self.assertEqual(trace._SPAN_EVENT_COUNT_LIMIT, 128)
        self.assertEqual(trace.SPAN_ATTRIBUTE_COUNT_LIMIT, 128)

        # import splunk_otel sets default envs for otel
        from splunk_otel import start_tracing  # pylint: disable=unused-import

        # reload otel module so it reads the env again
        reload(trace)
        self.assertEqual(trace._SPAN_LINK_COUNT_LIMIT, 1000)
        self.assertEqual(trace._SPAN_EVENT_COUNT_LIMIT, 999999)
        self.assertEqual(trace.SPAN_ATTRIBUTE_COUNT_LIMIT, 999999)
