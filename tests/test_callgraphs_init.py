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

from unittest.mock import patch

from splunk_otel.callgraphs import configure_callgraphs


class TestStartCallgraphsIfEnabled:
    @patch("splunk_otel.callgraphs.trace")
    @patch("splunk_otel.callgraphs.CallgraphsSpanProcessor")
    def test_adds_processor(self, mock_processor, mock_trace):
        configure_callgraphs("test-service", 10)

        mock_trace.get_tracer_provider.return_value.add_span_processor.assert_called_once()
        mock_processor.assert_called_once_with("test-service", 10)

    @patch("splunk_otel.callgraphs.trace")
    @patch("splunk_otel.callgraphs.CallgraphsSpanProcessor")
    def test_uses_custom_sampling_interval(self, mock_processor, mock_trace):
        configure_callgraphs("test-service", 50)

        mock_processor.assert_called_once_with("test-service", 50)
