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

from opentelemetry._opamp.client import OpAMPClient
from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry.environment_variables import OTEL_LOGS_EXPORTER
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.util._importlib_metadata import entry_points

from splunk_otel.env import (
    Env,
    SPLUNK_OPAMP_ENABLED,
    SPLUNK_OPAMP_ENDPOINT,
    SPLUNK_OPAMP_POLLING_INTERVAL,
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
)
from splunk_otel.opamp import (
    _build_client,
    _start_agent,
    build_effective_config_report,
    start_opamp,
)


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


def parse_properties(content):
    return dict(line.split("=", 1) for line in content.splitlines())


def test_opamp_post_sdk_entry_point_is_registered():
    [entry_point] = entry_points(group="_opentelemetry_opamp", name="post_sdk_init_function")

    assert entry_point.value == "splunk_otel.opamp:start_opamp"


def test_start_opamp_returns_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "splunk_otel.opamp._build_client",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected call")),
    )

    start_opamp(Resource.create({}))


def test_start_opamp_uses_defaults_when_enabled(monkeypatch):
    captured = {}

    monkeypatch.setenv(SPLUNK_OPAMP_ENABLED, "true")
    monkeypatch.setattr(
        "splunk_otel.opamp._build_client",
        lambda endpoint, _attributes: (captured.update(endpoint=endpoint) or FakeClient()),
    )
    monkeypatch.setattr(
        "splunk_otel.opamp._start_agent",
        lambda polling_interval_ms, _report, _client: captured.update(polling_interval_ms=polling_interval_ms),
    )

    start_opamp(Resource.create({}))

    assert captured == {
        "endpoint": "http://localhost:4320/v1/opamp",
        "polling_interval_ms": 30000,
    }


def test_start_opamp_uses_resource_from_sdk_hook(monkeypatch):
    resource = Resource.create({"service.name": "checkout"})
    captured = {}

    monkeypatch.setenv(SPLUNK_OPAMP_ENABLED, "true")
    monkeypatch.setenv(SPLUNK_OPAMP_ENDPOINT, "http://host/opamp")
    monkeypatch.setenv(SPLUNK_OPAMP_POLLING_INTERVAL, "2500")
    monkeypatch.setattr(
        "splunk_otel.opamp._build_client",
        lambda endpoint, attributes: (captured.update(endpoint=endpoint, attributes=attributes) or FakeClient()),
    )
    monkeypatch.setattr(
        "splunk_otel.opamp._start_agent",
        lambda polling_interval_ms, report, client: captured.update(
            polling_interval_ms=polling_interval_ms,
            report=report,
            client=client,
        ),
    )

    start_opamp(resource)

    assert captured["endpoint"] == "http://host/opamp"
    assert captured["polling_interval_ms"] == 2500
    assert captured["attributes"]["service.name"] == "checkout"
    assert captured["client"].effective_config_calls == []


def test_start_opamp_logs_start_exception(monkeypatch, caplog):
    monkeypatch.setenv(SPLUNK_OPAMP_ENABLED, "true")
    monkeypatch.setattr(
        "splunk_otel.opamp._build_client",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with caplog.at_level(logging.ERROR):
        start_opamp(Resource.create({}))

    assert "Failed to start OpAMP client" in caplog.text


def test_start_agent_reports_effective_config_and_starts_agent():
    client = FakeClient()

    agent = _start_agent(
        5000,
        f"{SPLUNK_PROFILER_ENABLED}=false",
        client,
        agent_factory=FakeAgent,
    )

    assert client.effective_config_calls == [
        (
            {"environment": f"{SPLUNK_PROFILER_ENABLED}=false"},
            "text/plain; format=properties; vendor=splunk; v=1.0.0",
        )
    ]
    assert agent.init_kwargs["interval"] == 5
    assert agent.started


def test_start_agent_builds_upstream_effective_config_message():
    class CapturingOpAMPClient(OpAMPClient):
        effective_config = None

        def update_effective_config(self, config, content_type):
            self.effective_config = super().update_effective_config(config, content_type)
            return self.effective_config

    client = CapturingOpAMPClient(
        endpoint="http://host/opamp",
        headers={},
        agent_identifying_attributes={},
        agent_non_identifying_attributes={},
    )

    _start_agent(
        30000,
        f"{SPLUNK_PROFILER_ENABLED}=false",
        client,
        agent_factory=FakeAgent,
    )

    config_file = client.effective_config.config_map.config_map["environment"]
    assert config_file.content_type == "text/plain; format=properties; vendor=splunk; v=1.0.0"
    assert config_file.body == b"SPLUNK_PROFILER_ENABLED=false"


def test_client_partitions_resource_attributes_and_preserves_types():
    client = _build_client(
        "http://host/opamp",
        {
            "service.name": "checkout",
            "service.namespace": "store",
            "service.instance.id": "checkout-1",
            "process.pid": 999,
            "host.name": "host-1",
        },
        client_factory=FakeClient,
    )

    assert client.init_kwargs["agent_identifying_attributes"] == {
        "service.name": "checkout",
        "service.namespace": "store",
        "service.instance.id": "checkout-1",
    }
    assert client.init_kwargs["agent_non_identifying_attributes"] == {
        "process.pid": 999,
        "host.name": "host-1",
    }


def test_client_serializes_resource_attribute_arrays():
    resource = Resource(
        {
            "service.name": "checkout",
            "host.ip": ["10.0.0.12", "127.0.0.1"],
            "custom.flags": [True, False],
            "custom.ports": [4317, 4318],
            "custom.ratios": [0.5, 1.5],
        }
    )

    client = _build_client(
        "http://host/opamp",
        resource.attributes,
    )
    message = opamp_pb2.AgentToServer()
    message.ParseFromString(client.build_full_state_message())
    attributes = {attribute.key: attribute.value for attribute in message.agent_description.non_identifying_attributes}

    assert attributes["host.ip"].string_value == '["10.0.0.12","127.0.0.1"]'
    assert attributes["custom.flags"].string_value == "[true,false]"
    assert attributes["custom.ports"].string_value == "[4317,4318]"
    assert attributes["custom.ratios"].string_value == "[0.5,1.5]"


def test_client_skips_unsupported_resource_attribute(caplog):
    with caplog.at_level(logging.WARNING):
        client = _build_client(
            "http://host/opamp",
            {
                "service.name": "checkout",
                "custom.mapping": {"nested": True},
            },
            client_factory=FakeClient,
        )

    assert client.init_kwargs["agent_identifying_attributes"] == {"service.name": "checkout"}
    assert client.init_kwargs["agent_non_identifying_attributes"] == {}
    assert "Skipping OpAMP resource attribute custom.mapping with unsupported type dict" in caplog.text


def test_effective_config_report_uses_defaults():
    assert parse_properties(build_effective_config_report(Env({}))) == {
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://localhost:4317",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://localhost:4317",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:4317",
        "SPLUNK_PROFILER_ENABLED": "false",
        "SPLUNK_PROFILER_MEMORY_ENABLED": "false",
        "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
        "SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL": "10",
        "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "1000",
        "OTEL_CONFIG_FILE": "null",
        "OTEL_EXPERIMENTAL_CONFIG_FILE": "null",
    }


def test_effective_config_report_uses_configured_splunk_values():
    report = parse_properties(
        build_effective_config_report(
            Env(
                {
                    SPLUNK_PROFILER_ENABLED: "true",
                    SPLUNK_PROFILER_CALL_STACK_INTERVAL: "500",
                    SPLUNK_SNAPSHOT_PROFILER_ENABLED: "true",
                    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL: "25",
                }
            )
        )
    )

    assert report[SPLUNK_PROFILER_ENABLED] == "true"
    assert report[SPLUNK_PROFILER_CALL_STACK_INTERVAL] == "500"
    assert report[SPLUNK_SNAPSHOT_PROFILER_ENABLED] == "true"
    assert report["SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL"] == "25"


def test_effective_config_report_uses_signal_specific_endpoints():
    report = parse_properties(
        build_effective_config_report(
            Env(
                {
                    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: "https://traces.example.com",
                    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: "https://metrics.example.com",
                    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: "https://logs.example.com",
                }
            )
        )
    )

    assert report[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "https://traces.example.com"
    assert report[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT] == "https://metrics.example.com"
    assert report[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "https://logs.example.com"


def test_effective_config_report_appends_http_signal_paths():
    report = parse_properties(
        build_effective_config_report(
            Env(
                {
                    OTEL_EXPORTER_OTLP_ENDPOINT: "https://collector:4318",
                    OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf",
                }
            )
        )
    )

    assert report[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "https://collector:4318/v1/traces"
    assert report[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT] == "https://collector:4318/v1/metrics"
    assert report[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "https://collector:4318/v1/logs"


def test_effective_config_report_honors_signal_protocol_and_exporter():
    report = parse_properties(
        build_effective_config_report(
            Env(
                {
                    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL: "http/protobuf",
                    OTEL_LOGS_EXPORTER: "otlp_proto_http",
                }
            )
        )
    )

    assert report[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "http://localhost:4317"
    assert report[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT] == "http://localhost:4318/v1/metrics"
    assert report[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "http://localhost:4318/v1/logs"
