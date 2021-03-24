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
from unittest import TestCase, mock

from splunk_otel.options import splunk_env_var


class TestOptions(TestCase):
    @mock.patch.dict(
        os.environ, {"SPLK_OLD_VAR": "OLD_VALUE", "SPLUNK_NEW_VAR": "NEW_VALUE"}
    )
    def test_from_env(self):
        self.assertIsNone(splunk_env_var("TEST_VAR1"))
        self.assertEqual(splunk_env_var("TEST_VAR1", "default value"), "default value")

        with self.assertLogs(level=logging.WARNING) as warning:
            self.assertEqual(splunk_env_var("OLD_VAR"), "OLD_VALUE")
            self.assertIn(
                "SPLK_OLD_VAR is deprecated and will be removed soon. Please use SPLUNK_OLD_VAR instead",
                warning.output[0],
            )
        self.assertEqual(splunk_env_var("NEW_VAR"), "NEW_VALUE")
