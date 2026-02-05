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

from splunk_otel.callgraphs import _configure_callgraphs_if_enabled
from splunk_otel.env import Env


class TestStartCallgraphsIfEnabled:
    @patch("splunk_otel.callgraphs.trace")
    def test_does_not_add_processor_when_disabled(self, mock_trace):
        env_store = {}
        env = Env(env_store)

        _configure_callgraphs_if_enabled(env)

        mock_trace.get_tracer_provider.return_value.add_span_processor.assert_not_called()

    @patch("splunk_otel.callgraphs.trace")
    @patch("splunk_otel.callgraphs.CallgraphsSpanProcessor")
    def test_adds_processor_when_enabled(self, mock_processor, mock_trace):
        env_store = {
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
            "OTEL_SERVICE_NAME": "test-service",
        }
        env = Env(env_store)

        _configure_callgraphs_if_enabled(env)

        mock_trace.get_tracer_provider.return_value.add_span_processor.assert_called_once()
        mock_processor.assert_called_once_with("test-service", 10)

    @patch("splunk_otel.callgraphs.trace")
    @patch("splunk_otel.callgraphs.CallgraphsSpanProcessor")
    def test_uses_custom_sampling_interval(self, mock_processor, mock_trace):
        env_store = {
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
            "OTEL_SERVICE_NAME": "test-service",
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "50",
        }
        env = Env(env_store)

        _configure_callgraphs_if_enabled(env)

        mock_processor.assert_called_once_with("test-service", 50)
