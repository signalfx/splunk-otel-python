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
from opentelemetry.instrumentation.propagators import get_global_response_propagator, set_global_response_propagator
from splunk_otel.distro import SplunkDistro
from splunk_otel.env import Env


def test_distro_env():
    env_store = {}
    configure_distro(env_store)
    assert env_store["OTEL_TRACES_EXPORTER"] == "otlp"
    assert len(env_store) == 14


def test_access_token():
    env_store = {"SPLUNK_ACCESS_TOKEN": "abc123"}
    configure_distro(env_store)
    assert env_store["OTEL_EXPORTER_OTLP_HEADERS"] == "x-sf-token=abc123"


def test_access_token_none():
    env_store = {}
    configure_distro(env_store)
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env_store


def test_access_token_empty():
    env_store = {"SPLUNK_ACCESS_TOKEN": ""}
    configure_distro(env_store)
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env_store


def test_access_token_whitespace():
    env_store = {"SPLUNK_ACCESS_TOKEN": " "}
    configure_distro(env_store)
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env_store


def test_server_timing_resp_prop_default():
    set_global_response_propagator(None)
    env_store = {}
    configure_distro(env_store)
    assert get_global_response_propagator()


def test_server_timing_resp_prop_true():
    set_global_response_propagator(None)
    env_store = {"SPLUNK_TRACE_RESPONSE_HEADER_ENABLED": "true"}
    configure_distro(env_store)
    assert get_global_response_propagator()


def test_server_timing_resp_prop_false():
    set_global_response_propagator(None)
    env_store = {"SPLUNK_TRACE_RESPONSE_HEADER_ENABLED": "false"}
    configure_distro(env_store)
    assert get_global_response_propagator() is None


def test_profiling_enabled():
    env_store = {"SPLUNK_PROFILER_ENABLED": "true"}
    configure_distro(env_store)
    assert env_store["OTEL_LOGS_ENABLED"] == "true"
    assert env_store["OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"] == "true"


def test_profiling_disabled():
    env_store = {"SPLUNK_PROFILER_ENABLED": "false"}
    configure_distro(env_store)
    assert "OTEL_LOGS_ENABLED" not in env_store
    assert "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED" not in env_store


def test_profiling_notset():
    env_store = {}
    configure_distro(env_store)
    assert "OTEL_LOGS_ENABLED" not in env_store
    assert "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED" not in env_store


def configure_distro(env_store):
    sd = SplunkDistro()
    sd.env = Env(env_store)
    sd.configure()
