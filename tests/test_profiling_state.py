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

from splunk_otel.env import Env
from splunk_otel.profile import ProfilingState, _start_profiling_if_enabled


class TestProfilingState:
    def _make_ctx(self, running, interval_seconds):
        ctx = MagicMock()
        ctx.running = running
        ctx.interval_seconds = interval_seconds
        return ctx

    def test_is_enabled_false_when_no_ctx(self):
        state = ProfilingState(None, 1000)
        assert state.is_enabled() is False

    def test_is_enabled_false_when_timer_not_running(self):
        state = ProfilingState(self._make_ctx(running=False, interval_seconds=1.0), 1000)
        assert state.is_enabled() is False

    def test_is_enabled_true_when_timer_running(self):
        state = ProfilingState(self._make_ctx(running=True, interval_seconds=1.0), 1000)
        assert state.is_enabled() is True

    def test_interval_millis_from_default_when_no_ctx(self):
        state = ProfilingState(None, 2000)
        assert state.interval_millis() == 2000

    def test_interval_millis_from_live_timer_when_running(self):
        state = ProfilingState(self._make_ctx(running=True, interval_seconds=0.5), 1000)
        assert state.interval_millis() == 500


class TestStartProfilingIfEnabled:
    def test_disabled_returns_state_with_is_enabled_false(self):
        env = Env({})
        state = _start_profiling_if_enabled(env)
        assert state.is_enabled() is False

    def test_disabled_returns_state_with_default_interval(self):
        env = Env({})
        state = _start_profiling_if_enabled(env)
        assert state.interval_millis() == 1000

    def test_disabled_respects_custom_interval_env_var(self):
        env = Env({"SPLUNK_PROFILER_CALL_STACK_INTERVAL": "500"})
        state = _start_profiling_if_enabled(env)
        assert state.interval_millis() == 500

    @patch("splunk_otel.profile.start_profiling")
    def test_enabled_returns_state_wrapping_ctx(self, mock_start):
        ctx = MagicMock()
        ctx.running = True
        ctx.interval_seconds = 1.0
        mock_start.return_value = ctx

        env = Env({"SPLUNK_PROFILER_ENABLED": "true"})
        state = _start_profiling_if_enabled(env)

        assert state.is_enabled() is True
        assert state.interval_millis() == 1000
        mock_start.assert_called_once_with(env)
