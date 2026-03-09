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

from unittest.mock import MagicMock, patch

from splunk_otel.callgraphs import CallgraphsState, _configure_callgraphs_if_enabled
from splunk_otel.env import Env


class TestCallgraphsState:
    def _make_processor(self, interval_millis):
        processor = MagicMock()
        processor.interval_millis.return_value = interval_millis
        return processor

    def test_is_enabled_false_when_no_processor(self):
        state = CallgraphsState(None, 10)
        assert state.is_enabled() is False

    def test_is_enabled_true_when_processor_present(self):
        state = CallgraphsState(self._make_processor(10), 10)
        assert state.is_enabled() is True

    def test_interval_from_default_when_no_processor(self):
        state = CallgraphsState(None, 10)
        assert state.interval() == 10

    def test_interval_from_live_timer_when_processor_present(self):
        state = CallgraphsState(self._make_processor(interval_millis=50), 10)
        assert state.interval() == 50


class TestConfigureCallgraphsIfEnabled:
    @patch("splunk_otel.callgraphs.trace")
    def test_disabled_returns_state_with_is_enabled_false(self, mock_trace):
        state = _configure_callgraphs_if_enabled(Env({}))
        assert state.is_enabled() is False
        mock_trace.get_tracer_provider.return_value.add_span_processor.assert_not_called()

    @patch("splunk_otel.callgraphs.trace")
    def test_disabled_returns_default_interval(self, mock_trace):
        state = _configure_callgraphs_if_enabled(Env({}))
        assert state.interval() == 10

    @patch("splunk_otel.callgraphs.trace")
    def test_disabled_respects_custom_interval_env_var(self, mock_trace):
        state = _configure_callgraphs_if_enabled(Env({"SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "50"}))
        assert state.interval() == 50

    @patch("splunk_otel.callgraphs.trace")
    @patch("splunk_otel.callgraphs.CallgraphsSpanProcessor")
    def test_enabled_returns_state_with_is_enabled_true(self, mock_processor_cls, mock_trace):
        mock_processor_cls.return_value.interval_millis.return_value = 10
        env = Env({"SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true", "OTEL_SERVICE_NAME": "svc"})

        state = _configure_callgraphs_if_enabled(env)

        assert state.is_enabled() is True
        mock_trace.get_tracer_provider.return_value.add_span_processor.assert_called_once()

    @patch("splunk_otel.callgraphs.trace")
    @patch("splunk_otel.callgraphs.CallgraphsSpanProcessor")
    def test_enabled_passes_interval_to_processor(self, mock_processor_cls, mock_trace):
        mock_processor_cls.return_value.interval_millis.return_value = 50
        env = Env(
            {
                "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
                "OTEL_SERVICE_NAME": "svc",
                "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "50",
            }
        )

        _configure_callgraphs_if_enabled(env)

        mock_processor_cls.assert_called_once_with("svc", 50)
