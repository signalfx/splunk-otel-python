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

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
from opentelemetry._opamp.client import OpAMPClient
from opentelemetry.environment_variables import (
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
)

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

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.util.types import AnyValue

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "environment"
_CONFIG_CONTENT_TYPE = "text/plain; format=properties; vendor=splunk; v=1.0.0"
_DEFAULT_OPAMP_ENDPOINT = "http://localhost:4320/v1/opamp"
_DEFAULT_OPAMP_POLLING_INTERVAL_MS = 30000
_DEFAULT_PROFILER_CALL_STACK_INTERVAL = 1000
_DEFAULT_SNAPSHOT_SAMPLING_INTERVAL = 10
_DEFAULT_GRPC_ENDPOINT = "http://localhost:4317"
_DEFAULT_HTTP_ENDPOINT = "http://localhost:4318/"
_OTLP_PROTOCOL_HTTP_PROTOBUF = "http/protobuf"
_OTLP_EXPORTER = "otlp"
_OTLP_PROTO_HTTP_EXPORTER = "otlp_proto_http"

_SPLUNK_PROFILER_MEMORY_ENABLED = "SPLUNK_PROFILER_MEMORY_ENABLED"
_SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL = (
    "SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL"
)
_OTEL_CONFIG_FILE = "OTEL_CONFIG_FILE"
_OTEL_EXPERIMENTAL_CONFIG_FILE = "OTEL_EXPERIMENTAL_CONFIG_FILE"

_SIGNAL_CONFIG = {
    "traces": {
        "endpoint": OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
        "protocol": OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
        "exporter": OTEL_TRACES_EXPORTER,
    },
    "metrics": {
        "endpoint": OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
        "protocol": OTEL_EXPORTER_OTLP_METRICS_PROTOCOL,
        "exporter": OTEL_METRICS_EXPORTER,
    },
    "logs": {
        "endpoint": OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
        "protocol": OTEL_EXPORTER_OTLP_LOGS_PROTOCOL,
        "exporter": OTEL_LOGS_EXPORTER,
    },
}


@dataclass(frozen=True)
class OpAMPConfig:
    endpoint: str
    polling_interval_ms: int

    @classmethod
    def from_env(cls, env: Env) -> OpAMPConfig | None:
        if not env.is_true(SPLUNK_OPAMP_ENABLED):
            logger.debug("OpAMP disabled (%s is not true)", SPLUNK_OPAMP_ENABLED)
            return None

        return cls(
            endpoint=env.getval(SPLUNK_OPAMP_ENDPOINT, _DEFAULT_OPAMP_ENDPOINT),
            polling_interval_ms=env.getint(
                SPLUNK_OPAMP_POLLING_INTERVAL,
                _DEFAULT_OPAMP_POLLING_INTERVAL_MS,
            ),
        )


class _SplunkCallbacks(OpAMPCallbacks):
    def on_connect_failed(
        self,
        _agent: OpAMPAgent,
        _client: OpAMPClient,
        error: Exception,
    ) -> None:
        logger.warning("Connection to OpAMP server failed", exc_info=error)

    def on_error(
        self,
        _agent: OpAMPAgent,
        _client: OpAMPClient,
        error_response,
    ) -> None:
        logger.warning("OpAMP server returned error: %s", error_response)

    def on_message(
        self,
        _agent: OpAMPAgent,
        _client: OpAMPClient,
        message: MessageData,
    ) -> None:
        logger.debug(
            "ServerToAgent message received: remote_config=%s",
            message.remote_config is not None,
        )


def start_opamp(resource: Resource) -> None:
    """Start the Splunk OpAMP agent after the OpenTelemetry SDK starts."""
    env = Env()
    config = OpAMPConfig.from_env(env)
    if config is None:
        return

    try:
        client = _build_client(config, resource.attributes)
        _start_agent(config, build_effective_config_report(env), client)
    except Exception:
        logger.exception("Failed to start OpAMP client")


def build_effective_config_report(env: Env) -> str:
    values = (
        (OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, _get_signal_endpoint(env, "traces")),
        (OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, _get_signal_endpoint(env, "metrics")),
        (OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, _get_signal_endpoint(env, "logs")),
        (
            SPLUNK_PROFILER_ENABLED,
            _bool_to_str(value=env.is_true(SPLUNK_PROFILER_ENABLED)),
        ),
        (_SPLUNK_PROFILER_MEMORY_ENABLED, "false"),
        (
            SPLUNK_SNAPSHOT_PROFILER_ENABLED,
            _bool_to_str(value=env.is_true(SPLUNK_SNAPSHOT_PROFILER_ENABLED)),
        ),
        (
            _SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL,
            str(
                env.getint(
                    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
                    _DEFAULT_SNAPSHOT_SAMPLING_INTERVAL,
                )
            ),
        ),
        (
            SPLUNK_PROFILER_CALL_STACK_INTERVAL,
            str(
                env.getint(
                    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
                    _DEFAULT_PROFILER_CALL_STACK_INTERVAL,
                )
            ),
        ),
        (_OTEL_CONFIG_FILE, "null"),
        (_OTEL_EXPERIMENTAL_CONFIG_FILE, "null"),
    )
    return "\n".join(f"{key}={value}" for key, value in values)


def _build_client(
    config: OpAMPConfig,
    resource_attributes: Mapping[str, AnyValue],
    client_factory=OpAMPClient,
):
    identifying_attributes = {
        str(key): str(value) for key, value in resource_attributes.items()
    }
    return client_factory(
        endpoint=config.endpoint,
        headers={},
        agent_identifying_attributes=identifying_attributes,
        agent_non_identifying_attributes={},
    )


def _start_agent(
    config: OpAMPConfig,
    effective_config_report: str,
    client,
    agent_factory=OpAMPAgent,
):
    client.update_effective_config(
        {_CONFIG_FILENAME: effective_config_report},
        content_type=_CONFIG_CONTENT_TYPE,
    )
    agent = agent_factory(
        interval=config.polling_interval_ms / 1000,
        callbacks=_SplunkCallbacks(),
        client=client,
    )
    agent.start()
    logger.info("OpAMP client started: %s", config.endpoint)
    return agent


def _get_signal_endpoint(env: Env, signal: str) -> str:
    signal_config = _SIGNAL_CONFIG[signal]
    endpoint = env.getval(signal_config["endpoint"])
    if endpoint:
        return endpoint

    base_endpoint = env.getval(OTEL_EXPORTER_OTLP_ENDPOINT)
    if _uses_http_protobuf(env, signal):
        return _append_signal_path(base_endpoint or _DEFAULT_HTTP_ENDPOINT, signal)

    return base_endpoint or _DEFAULT_GRPC_ENDPOINT


def _uses_http_protobuf(env: Env, signal: str) -> bool:
    signal_config = _SIGNAL_CONFIG[signal]
    protocol = env.getval(signal_config["protocol"]) or env.getval(
        OTEL_EXPORTER_OTLP_PROTOCOL
    )
    if protocol:
        return protocol.strip() == _OTLP_PROTOCOL_HTTP_PROTOBUF

    exporter = env.getval(signal_config["exporter"], _OTLP_EXPORTER).strip()
    return exporter == _OTLP_PROTO_HTTP_EXPORTER


def _append_signal_path(endpoint: str, signal: str) -> str:
    signal_path = f"v1/{signal}"
    if endpoint.endswith(signal_path):
        return endpoint
    if not endpoint.endswith("/"):
        endpoint += "/"
    return endpoint + signal_path


def _bool_to_str(*, value: bool) -> str:
    return "true" if value else "false"
