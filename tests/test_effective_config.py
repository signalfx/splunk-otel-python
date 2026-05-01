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

import pytest
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_HEADERS,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
)

from splunk_otel.effective_config import DEFAULT_SERVICE_NAME, build_effective_config
from splunk_otel.env import (
    Env,
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_REALM,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SELECTION_PROBABILITY,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
)


def test_apply_upstream_to_env_materializes_only_upstream_values():
    env_store = {}
    env = Env(env_store)

    build_effective_config(env).apply_upstream_to_env(env)

    assert env_store["OTEL_SERVICE_NAME"] == DEFAULT_SERVICE_NAME
    assert env_store[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == "http://localhost:4317"
    assert env_store[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT] == "http://localhost:4317"
    assert env_store[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "http://localhost:4317"
    assert SPLUNK_PROFILER_CALL_STACK_INTERVAL not in env_store
    assert SPLUNK_SNAPSHOT_SAMPLING_INTERVAL not in env_store


def test_realm_materializes_distro_resolved_values():
    env_store = {SPLUNK_REALM: "us2"}
    env = Env(env_store)

    build_effective_config(env).apply_upstream_to_env(env)

    assert env_store[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT] == (
        "https://ingest.us2.observability.splunkcloud.com/v2/trace/otlp"
    )
    assert env_store[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT] == (
        "https://ingest.us2.observability.splunkcloud.com/v2/datapoint/otlp"
    )
    assert env_store[OTEL_EXPORTER_OTLP_PROTOCOL] == "http/protobuf"
    assert env_store[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] == "http://localhost:4318/v1/logs"


def test_access_token_materializes_otlp_headers():
    env_store = {SPLUNK_ACCESS_TOKEN: "abc123"}
    env = Env(env_store)

    build_effective_config(env).apply_upstream_to_env(env)

    assert env_store["OTEL_EXPORTER_OTLP_HEADERS"] == "x-sf-token=abc123"


def test_access_token_appends_to_existing_otlp_headers():
    config = build_effective_config(
        Env(
            {
                OTEL_EXPORTER_OTLP_HEADERS: "existing=value",
                SPLUNK_ACCESS_TOKEN: "abc123",
            }
        )
    )

    assert config.upstream_env[OTEL_EXPORTER_OTLP_HEADERS] == "existing=value,x-sf-token=abc123"


def test_explicit_signal_endpoint_wins_over_realm():
    config = build_effective_config(
        Env(
            {
                SPLUNK_REALM: "us2",
                OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: "http://collector:4317",
            }
        )
    )

    assert config.otlp_traces_endpoint == "http://collector:4317"
    assert config.otlp_metrics_endpoint == "https://ingest.us2.observability.splunkcloud.com/v2/datapoint/otlp"


def test_http_base_endpoint_appends_signal_paths():
    config = build_effective_config(
        Env(
            {
                OTEL_EXPORTER_OTLP_ENDPOINT: "http://collector:4318",
                OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf",
            }
        )
    )

    assert config.otlp_traces_endpoint == "http://collector:4318/v1/traces"
    assert config.otlp_metrics_endpoint == "http://collector:4318/v1/metrics"
    assert config.otlp_logs_endpoint == "http://collector:4318/v1/logs"


def test_signal_protocol_controls_default_endpoint():
    config = build_effective_config(Env({OTEL_EXPORTER_OTLP_TRACES_PROTOCOL: "http/protobuf"}))

    assert config.otlp_traces_endpoint == "http://localhost:4318/v1/traces"
    assert config.otlp_metrics_endpoint == "http://localhost:4317"


def test_resource_attributes_append_distro_attributes():
    config = build_effective_config(Env({OTEL_RESOURCE_ATTRIBUTES: "foo=bar"}))

    assert config.upstream_env[OTEL_RESOURCE_ATTRIBUTES].startswith("foo=bar,")
    assert "telemetry.distro.name=splunk-opentelemetry" in config.upstream_env[OTEL_RESOURCE_ATTRIBUTES]
    assert "telemetry.distro.version=" in config.upstream_env[OTEL_RESOURCE_ATTRIBUTES]


def test_profiling_logs_endpoint_requires_profiling_enabled():
    disabled = build_effective_config(Env({"SPLUNK_PROFILER_LOGS_ENDPOINT": "my-logs-endpoint"}))
    enabled = build_effective_config(
        Env(
            {
                SPLUNK_PROFILER_ENABLED: "true",
                "SPLUNK_PROFILER_LOGS_ENDPOINT": "my-logs-endpoint",
            }
        )
    )
    snapshot_enabled = build_effective_config(
        Env(
            {
                SPLUNK_SNAPSHOT_PROFILER_ENABLED: "true",
                "SPLUNK_PROFILER_LOGS_ENDPOINT": "snapshot-logs-endpoint",
            }
        )
    )

    assert disabled.otlp_logs_endpoint == "http://localhost:4317"
    assert enabled.otlp_logs_endpoint == "my-logs-endpoint"
    assert snapshot_enabled.otlp_logs_endpoint == "snapshot-logs-endpoint"


def test_splunk_values_are_coerced_when_effective_config_is_built():
    config = build_effective_config(
        Env(
            {
                SPLUNK_PROFILER_ENABLED: "true",
                SPLUNK_PROFILER_CALL_STACK_INTERVAL: "500",
                SPLUNK_SNAPSHOT_PROFILER_ENABLED: "true",
                SPLUNK_SNAPSHOT_SAMPLING_INTERVAL: "25",
                SPLUNK_SNAPSHOT_SELECTION_PROBABILITY: "0.5",
            }
        )
    )

    assert config.profiler_enabled is True
    assert config.profiler_call_stack_interval == 500
    assert config.snapshot_profiler_enabled is True
    assert config.snapshot_sampling_interval == 25
    assert config.snapshot_selection_probability == 0.5


def test_upstream_only_values_stay_in_read_only_env_map():
    config = build_effective_config(Env({}))

    assert config.upstream_env[OTEL_SPAN_LINK_COUNT_LIMIT] == "1000"
    assert isinstance(config.upstream_env[OTEL_SPAN_LINK_COUNT_LIMIT], str)
    assert not hasattr(config, "span_link_count_limit")

    with pytest.raises(TypeError):
        config.upstream_env[OTEL_SPAN_LINK_COUNT_LIMIT] = "2000"
