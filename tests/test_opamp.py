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

from splunk_otel.env import (
    Env,
    SPLUNK_OPAMP_ENABLED,
    SPLUNK_OPAMP_ENDPOINT,
)
from splunk_otel.opamp import _start_opamp_if_enabled
from splunk_otel.opamp.config_registry import ConfigRegistry


class FakeClient:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.effective_config_calls = []

    def update_effective_config(self, config, content_type):
        self.effective_config_calls.append((config, content_type))


class FakeAgent:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True


def _registry(**kv):
    r = ConfigRegistry()
    for k, v in kv.items():
        r.register(k, getter=lambda val=v: val)
    return r


_MINIMAL_RESOURCE_ATTRS = {
    "service.name": "my-svc",
    "telemetry.sdk.version": "1.39.0",
}


class TestStartOpampIfEnabled:
    def test_returns_none_when_disabled(self):
        assert _start_opamp_if_enabled({}, _registry(), Env(store={})) is None

    def test_returns_agent_when_enabled(self):
        env = Env(
            store={
                SPLUNK_OPAMP_ENABLED: "true",
                SPLUNK_OPAMP_ENDPOINT: "http://host/opamp",
            }
        )
        result = _start_opamp_if_enabled(
            _MINIMAL_RESOURCE_ATTRS,
            _registry(),
            env,
            client_factory=FakeClient,
            agent_factory=FakeAgent,
        )
        assert isinstance(result, FakeAgent)
        assert result.started

    def test_returns_none_on_exception(self, caplog):
        def exploding_client(**_kwargs):
            msg = "boom"
            raise RuntimeError(msg)

        env = Env(
            store={
                SPLUNK_OPAMP_ENABLED: "true",
                SPLUNK_OPAMP_ENDPOINT: "http://host/opamp",
            }
        )
        with caplog.at_level(logging.ERROR):
            result = _start_opamp_if_enabled({}, _registry(), env, client_factory=exploding_client)
        assert result is None
        assert "Failed to start OpAMP client" in caplog.text


class TestAgentAttributes:
    def test_all_resource_attrs_sent_as_identifying(self):
        env = Env(
            store={
                SPLUNK_OPAMP_ENABLED: "true",
                SPLUNK_OPAMP_ENDPOINT: "http://host/opamp",
            }
        )
        resource_attrs = {
            "service.name": "my-svc",
            "os.type": "linux",
            "host.name": "myhost",
            "process.pid": 12345,
            "deployment.environment.name": "prod",
        }
        client = None

        def capture_client(**kwargs):
            nonlocal client
            client = FakeClient(**kwargs)
            return client

        _start_opamp_if_enabled(
            resource_attrs,
            _registry(),
            env,
            client_factory=capture_client,
            agent_factory=FakeAgent,
        )
        identifying = client.init_kwargs["agent_identifying_attributes"]
        non_identifying = client.init_kwargs["agent_non_identifying_attributes"]

        assert identifying["service.name"] == "my-svc"
        assert identifying["os.type"] == "linux"
        assert identifying["host.name"] == "myhost"
        assert identifying["process.pid"] == "12345"
        assert identifying["deployment.environment.name"] == "prod"
        assert non_identifying == {}

    def test_values_are_stringified(self):
        env = Env(
            store={
                SPLUNK_OPAMP_ENABLED: "true",
                SPLUNK_OPAMP_ENDPOINT: "http://host/opamp",
            }
        )
        client = None

        def capture_client(**kwargs):
            nonlocal client
            client = FakeClient(**kwargs)
            return client

        _start_opamp_if_enabled(
            {"process.pid": 999},
            _registry(),
            env,
            client_factory=capture_client,
            agent_factory=FakeAgent,
        )
        assert client.init_kwargs["agent_identifying_attributes"]["process.pid"] == "999"
