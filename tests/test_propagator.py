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

from opentelemetry.propagators import get_global_textmap
from opentelemetry.propagators.b3 import B3Format

from splunk_otel import tracing  # pylint:disable=C0415,W0611


class TestPropagator(unittest.TestCase):
    def test_splunk_otel_sets_b3_as_global_propagator(self):
        propagtor = get_global_textmap()
        self.assertIsInstance(propagtor, B3Format)
