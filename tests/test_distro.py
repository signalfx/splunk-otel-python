#  Copyright Splunk Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import logging

import pytest
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator

from splunk_otel.__about__ import __version__ as version
from splunk_otel.distro import EnvironmentConfiguration
from splunk_otel.env import Env
from splunk_otel.propagator import CallgraphsPropagator


def test_distro_env():
    env_store = {}
    configure_environment(env_store)
    assert env_store["OTEL_TRACES_EXPORTER"] == "otlp"
    assert len(env_store) > 10


def test_access_token():
    env_store = {"SPLUNK_ACCESS_TOKEN": "abc123"}
    configure_environment(env_store)
    assert env_store["OTEL_EXPORTER_OTLP_HEADERS"] == "x-sf-token=abc123"


def test_access_token_none():
    env_store = {}
    configure_environment(env_store)
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env_store


def test_access_token_empty():
    env_store = {"SPLUNK_ACCESS_TOKEN": ""}
    configure_environment(env_store)
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env_store


def test_access_token_whitespace():
    env_store = {"SPLUNK_ACCESS_TOKEN": " "}
    configure_environment(env_store)
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env_store


def test_profiling_endpt():
    env_store = {
        "SPLUNK_PROFILER_ENABLED": "true",
        "SPLUNK_PROFILER_LOGS_ENDPOINT": "my-logs-endpoint",
    }
    configure_environment(env_store)
    assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" in env_store


def test_snapshot_profiling_endpt():
    # SPLUNK_PROFILER_LOGS_ENDPOINT should also be forwarded when only snapshot
    # profiling is enabled. Old code only checked SPLUNK_PROFILER_ENABLED.
    env_store = {
        "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
        "SPLUNK_PROFILER_LOGS_ENDPOINT": "my-logs-endpoint",
    }
    configure_environment(env_store)
    assert env_store.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") == "my-logs-endpoint"


def test_resource_attributes():
    env_store = {"OTEL_RESOURCE_ATTRIBUTES": "foo=bar"}
    configure_environment(env_store)
    attrs = env_store["OTEL_RESOURCE_ATTRIBUTES"]
    assert "telemetry.distro.name=splunk-opentelemetry" in attrs
    assert f"telemetry.distro.version={version}" in attrs
    assert "foo=bar" in attrs


def test_service_name(caplog):
    with caplog.at_level(logging.WARNING):
        env_store = {}
        configure_environment(env_store)
        assert "OTEL_SERVICE_NAME" in env_store
    assert "service.name attribute is not set" in caplog.text


def test_realm():
    env_store = {"SPLUNK_REALM": "us2"}
    configure_environment(env_store)
    assert (
        env_store["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
        == "https://ingest.us2.observability.splunkcloud.com/v2/trace/otlp"
    )
    assert (
        env_store["OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"]
        == "https://ingest.us2.observability.splunkcloud.com/v2/datapoint/otlp"
    )
    assert env_store["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"


def test_realm_strips_whitespace():
    env_store = {"SPLUNK_REALM": " us2 "}
    configure_environment(env_store)
    assert (
        env_store["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
        == "https://ingest.us2.observability.splunkcloud.com/v2/trace/otlp"
    )


@pytest.mark.parametrize(
    "realm",
    [
        "attacker.test",
        "attacker.test/anything",
        "attacker.test:443/foo",
        "us2/anything",
        "us2:443",
        "-us2",
        "us2-",
    ],
)
def test_invalid_realm_is_ignored(caplog, realm):
    env_store = {"SPLUNK_REALM": realm}
    with caplog.at_level(logging.WARNING):
        configure_environment(env_store)
    assert "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT" not in env_store
    assert "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT" not in env_store
    assert "OTEL_EXPORTER_OTLP_PROTOCOL" not in env_store
    assert "Ignoring invalid SPLUNK_REALM value" in caplog.text


@pytest.mark.parametrize(
    "env_store",
    [
        {},
        {"SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true"},
        {"SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true", "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": "0.5"},
    ],
)
def test_environment_setup_leaves_snapshot_selection_to_controller(env_store):
    previous = get_global_textmap()
    propagator = CompositePropagator([CallgraphsPropagator(1.0)])
    set_global_textmap(propagator)
    try:
        configure_environment(env_store)
        assert get_global_textmap() is propagator
    finally:
        set_global_textmap(previous)


def configure_environment(env_store):
    EnvironmentConfiguration(Env(env_store)).configure()
