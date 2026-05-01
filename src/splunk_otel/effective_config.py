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

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_HEADERS,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)

from splunk_otel.__about__ import __version__ as version
from splunk_otel.env import (
    DEFAULTS,
    Env,
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_PROFILER_LOGS_ENDPOINT,
    SPLUNK_REALM,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SELECTION_PROBABILITY,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
    SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

DISTRO_NAME = "splunk-opentelemetry"
DEFAULT_SERVICE_NAME = "unnamed-python-service"
DEFAULT_PROFILER_CALL_STACK_INTERVAL = 1000
DEFAULT_SNAPSHOT_SAMPLING_INTERVAL = 10

_OTLP_PROTOCOL_GRPC = "grpc"
_OTLP_PROTOCOL_HTTP_PROTOBUF = "http/protobuf"
_OTLP_EXPORTER = "otlp"
_OTLP_PROTO_GRPC_EXPORTER = "otlp_proto_grpc"
_OTLP_PROTO_HTTP_EXPORTER = "otlp_proto_http"
_DEFAULT_GRPC_ENDPOINT = "http://localhost:4317"
_DEFAULT_HTTP_ENDPOINT = "http://localhost:4318/"
_X_SF_TOKEN = "x-sf-token"  # noqa S105
_DEFAULT_SNAPSHOT_SELECTION_PROBABILITY = 0.01

_SIGNAL_CONFIG = {
    "traces": {
        "endpoint": OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
        "protocol": OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
        "exporter": "OTEL_TRACES_EXPORTER",
    },
    "metrics": {
        "endpoint": OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
        "protocol": OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
        "exporter": "OTEL_METRICS_EXPORTER",
    },
    "logs": {
        "endpoint": OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
        "protocol": OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
        "exporter": "OTEL_LOGS_EXPORTER",
    },
}


@dataclass(frozen=True)
class EffectiveConfig:
    upstream_env: Mapping[str, str]
    service_name: str
    otlp_traces_endpoint: str
    otlp_metrics_endpoint: str
    otlp_logs_endpoint: str
    profiler_enabled: bool
    profiler_call_stack_interval: int
    snapshot_profiler_enabled: bool
    snapshot_sampling_interval: int
    snapshot_selection_probability: float
    trace_response_header_enabled: bool
    defaulted_service_name: bool = False

    def apply_upstream_to_env(self, env: Env) -> None:
        for key, value in self.upstream_env.items():
            env.setval(key, value)

    def to_upstream_env(self) -> dict[str, str]:
        return dict(self.upstream_env)


def build_effective_config(env: Env) -> EffectiveConfig:
    upstream_env = {key: env.getval(key, value) for key, value in DEFAULTS.items()}
    protocol = env.getval(OTEL_EXPORTER_OTLP_PROTOCOL)
    if protocol:
        upstream_env[OTEL_EXPORTER_OTLP_PROTOCOL] = protocol

    service_name = env.getval(OTEL_SERVICE_NAME)
    defaulted_service_name = not len(service_name)
    upstream_env[OTEL_SERVICE_NAME] = service_name or DEFAULT_SERVICE_NAME

    profiler_enabled = env.is_true(SPLUNK_PROFILER_ENABLED)
    profiler_call_stack_interval = env.getint(
        SPLUNK_PROFILER_CALL_STACK_INTERVAL,
        DEFAULT_PROFILER_CALL_STACK_INTERVAL,
    )
    snapshot_profiler_enabled = env.is_true(SPLUNK_SNAPSHOT_PROFILER_ENABLED)
    snapshot_sampling_interval = env.getint(SPLUNK_SNAPSHOT_SAMPLING_INTERVAL, DEFAULT_SNAPSHOT_SAMPLING_INTERVAL)
    snapshot_selection_probability = env.getfloat(
        SPLUNK_SNAPSHOT_SELECTION_PROBABILITY,
        _DEFAULT_SNAPSHOT_SELECTION_PROBABILITY,
    )
    trace_response_header_enabled = env.is_true(SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, "true")

    upstream_env[OTEL_RESOURCE_ATTRIBUTES] = _build_resource_attributes(env)
    upstream_env.update(_build_realm_config(env))

    profiling_logs_endpoint = _resolve_profiling_logs_endpoint(
        env,
        profiler_enabled=profiler_enabled,
        snapshot_profiler_enabled=snapshot_profiler_enabled,
    )
    if profiling_logs_endpoint:
        upstream_env[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT] = profiling_logs_endpoint

    token_headers = _build_token_headers(env)
    if token_headers:
        upstream_env[OTEL_EXPORTER_OTLP_HEADERS] = token_headers

    upstream_env.update(_resolve_otlp_endpoints(env, upstream_env))

    return EffectiveConfig(
        upstream_env=MappingProxyType(dict(upstream_env)),
        service_name=upstream_env[OTEL_SERVICE_NAME],
        otlp_traces_endpoint=upstream_env[OTEL_EXPORTER_OTLP_TRACES_ENDPOINT],
        otlp_metrics_endpoint=upstream_env[OTEL_EXPORTER_OTLP_METRICS_ENDPOINT],
        otlp_logs_endpoint=upstream_env[OTEL_EXPORTER_OTLP_LOGS_ENDPOINT],
        profiler_enabled=profiler_enabled,
        profiler_call_stack_interval=profiler_call_stack_interval,
        snapshot_profiler_enabled=snapshot_profiler_enabled,
        snapshot_sampling_interval=snapshot_sampling_interval,
        snapshot_selection_probability=snapshot_selection_probability,
        trace_response_header_enabled=trace_response_header_enabled,
        defaulted_service_name=defaulted_service_name,
    )


def _build_resource_attributes(env: Env) -> str:
    attrs = env.getval(OTEL_RESOURCE_ATTRIBUTES)
    attrs = _list_append(attrs, f"telemetry.distro.name={DISTRO_NAME}")
    return _list_append(attrs, f"telemetry.distro.version={version}")


def _build_realm_config(env: Env) -> dict[str, str]:
    realm = env.getval(SPLUNK_REALM)
    if not realm:
        return {}

    ingest_url = f"https://ingest.{realm}.observability.splunkcloud.com"
    return {
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: env.getval(
            OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
            f"{ingest_url}/v2/trace/otlp",
        ),
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: env.getval(
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
            f"{ingest_url}/v2/datapoint/otlp",
        ),
        OTEL_EXPORTER_OTLP_PROTOCOL: env.getval(OTEL_EXPORTER_OTLP_PROTOCOL, _OTLP_PROTOCOL_HTTP_PROTOBUF),
    }


def _resolve_profiling_logs_endpoint(
    env: Env,
    *,
    profiler_enabled: bool,
    snapshot_profiler_enabled: bool,
) -> str | None:
    if not (profiler_enabled or snapshot_profiler_enabled):
        return None

    logs_endpoint = env.getval(SPLUNK_PROFILER_LOGS_ENDPOINT)
    if logs_endpoint:
        return logs_endpoint
    return None


def _build_token_headers(env: Env) -> str | None:
    headers = env.getval(OTEL_EXPORTER_OTLP_HEADERS)
    token = env.getval(SPLUNK_ACCESS_TOKEN).strip()
    if token:
        headers = _list_append(headers, f"{_X_SF_TOKEN}={token}")
    if headers:
        return headers
    return None


def _resolve_otlp_endpoints(env: Env, values: Mapping[str, str]) -> dict[str, str]:
    endpoints = {}
    for signal in _SIGNAL_CONFIG:
        endpoint_key = _SIGNAL_CONFIG[signal]["endpoint"]
        if endpoint_key not in values:
            endpoints[endpoint_key] = _get_signal_endpoint(env, values, signal)
    return endpoints


def _get_signal_endpoint(env: Env, values: Mapping[str, str], signal: str) -> str:
    signal_config = _SIGNAL_CONFIG[signal]
    endpoint = values.get(signal_config["endpoint"]) or env.getval(signal_config["endpoint"])
    if endpoint:
        return endpoint

    base_endpoint = env.getval(OTEL_EXPORTER_OTLP_ENDPOINT)
    if _get_signal_protocol(env, values, signal) == _OTLP_PROTOCOL_HTTP_PROTOBUF:
        return _append_signal_path(base_endpoint or _DEFAULT_HTTP_ENDPOINT, signal)

    return base_endpoint or _DEFAULT_GRPC_ENDPOINT


def _get_signal_protocol(env: Env, values: Mapping[str, str], signal: str) -> str:
    signal_config = _SIGNAL_CONFIG[signal]
    protocol = (
        env.getval(signal_config["protocol"])
        or values.get(OTEL_EXPORTER_OTLP_PROTOCOL)
        or env.getval(OTEL_EXPORTER_OTLP_PROTOCOL)
    )
    if protocol:
        return protocol.strip()

    exporter = env.getval(signal_config["exporter"], _OTLP_EXPORTER).strip()
    if exporter == _OTLP_PROTO_HTTP_EXPORTER:
        return _OTLP_PROTOCOL_HTTP_PROTOBUF
    if exporter == _OTLP_PROTO_GRPC_EXPORTER:
        return _OTLP_PROTOCOL_GRPC
    return _OTLP_PROTOCOL_GRPC


def _append_signal_path(endpoint: str, signal: str) -> str:
    signal_path = f"v1/{signal}"
    if endpoint.endswith(signal_path):
        return endpoint
    if not endpoint.endswith("/"):
        endpoint += "/"
    return endpoint + signal_path


def _list_append(current: str, value: str) -> str:
    if current:
        return current + "," + value
    return value
