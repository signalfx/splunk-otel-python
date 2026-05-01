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

from __future__ import annotations

from typing import TYPE_CHECKING

from splunk_otel.effective_config import EffectiveConfig, build_effective_config

if TYPE_CHECKING:
    from splunk_otel.env import Env


class ConfigProvider:
    def __init__(self, effective_config: EffectiveConfig):
        self._effective_config = effective_config

    @classmethod
    def from_env(cls, env: Env) -> ConfigProvider:
        return cls(build_effective_config(env))

    def effective_config(self) -> EffectiveConfig:
        return self._effective_config

    def apply_upstream_to_env(self, env: Env) -> None:
        self._effective_config.apply_upstream_to_env(env)

    def upstream_env(self) -> dict[str, str]:
        return self._effective_config.to_upstream_env()

    def service_name(self) -> str:
        return self._effective_config.service_name

    def otlp_traces_endpoint(self) -> str:
        return self._effective_config.otlp_traces_endpoint

    def otlp_metrics_endpoint(self) -> str:
        return self._effective_config.otlp_metrics_endpoint

    def otlp_logs_endpoint(self) -> str:
        return self._effective_config.otlp_logs_endpoint

    def profiler_enabled(self) -> bool:
        return self._effective_config.profiler_enabled

    def profiler_call_stack_interval(self) -> int:
        return self._effective_config.profiler_call_stack_interval

    def snapshot_profiler_enabled(self) -> bool:
        return self._effective_config.snapshot_profiler_enabled

    def snapshot_sampling_interval(self) -> int:
        return self._effective_config.snapshot_sampling_interval

    def snapshot_selection_probability(self) -> float:
        return self._effective_config.snapshot_selection_probability

    def trace_response_header_enabled(self) -> bool:
        return self._effective_config.trace_response_header_enabled

    def defaulted_service_name(self) -> bool:
        return self._effective_config.defaulted_service_name


_current_config_provider: ConfigProvider | None = None


def get_config_provider(env: Env) -> ConfigProvider:
    global _current_config_provider  # noqa: PLW0603
    config_provider = _current_config_provider
    if config_provider is None:
        config_provider = ConfigProvider.from_env(env)
        _current_config_provider = config_provider
    return config_provider


def set_config_provider(config_provider: ConfigProvider) -> None:
    global _current_config_provider  # noqa: PLW0603
    _current_config_provider = config_provider


def reset_config_provider() -> None:
    global _current_config_provider  # noqa: PLW0603
    _current_config_provider = None
