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

from unittest.mock import Mock

import pytest

from splunk_otel import config_provider
from splunk_otel.config_provider import (
    ConfigProvider,
    get_config_provider,
    reset_config_provider,
    set_config_provider,
)
from splunk_otel.effective_config import build_effective_config
from splunk_otel.env import Env


@pytest.fixture(autouse=True)
def reset_provider():
    reset_config_provider()
    yield
    reset_config_provider()


def _provider(env=None):
    return ConfigProvider(build_effective_config(Env(env or {})))


def test_get_config_provider_builds_once(monkeypatch):
    effective_config = build_effective_config(Env({"OTEL_SERVICE_NAME": "fallback"}))
    build = Mock(return_value=effective_config)
    monkeypatch.setattr(config_provider, "build_effective_config", build)
    env = Env({"OTEL_SERVICE_NAME": "ignored-after-first-call"})

    provider = get_config_provider(env)

    assert provider.effective_config() is effective_config
    assert get_config_provider(env) is provider
    build.assert_called_once_with(env)


def test_set_config_provider_replaces_current_provider():
    first = _provider({"OTEL_SERVICE_NAME": "first"})
    second = _provider({"OTEL_SERVICE_NAME": "second"})
    env = Env({})

    set_config_provider(first)
    assert get_config_provider(env) is first

    set_config_provider(second)
    assert get_config_provider(env) is second


def test_config_provider_exposes_typed_values():
    provider = _provider(
        {
            "OTEL_SERVICE_NAME": "svc",
            "SPLUNK_PROFILER_ENABLED": "true",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "500",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "25",
            "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": "0.5",
        }
    )

    assert provider.service_name() == "svc"
    assert provider.profiler_enabled() is True
    assert provider.profiler_call_stack_interval() == 500
    assert provider.snapshot_profiler_enabled() is True
    assert provider.snapshot_sampling_interval() == 25
    assert provider.snapshot_selection_probability() == 0.5
