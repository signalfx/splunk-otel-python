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

from opentelemetry.sdk.resources import (
    TELEMETRY_SDK_LANGUAGE,
    TELEMETRY_SDK_NAME,
    TELEMETRY_SDK_VERSION,
)
from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.client import OpAMPClient
from opentelemetry._opamp.proto import opamp_pb2

from splunk_otel.env import (
    Env,
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_OPAMP_ENABLED,
    SPLUNK_OPAMP_ENDPOINT,
    SPLUNK_OPAMP_POLLING_INTERVAL,
    SPLUNK_OPAMP_TOKEN,
)
from splunk_otel.distro import _DISTRO_NAME
from splunk_otel.opamp.config_registry import ConfigRegistry

logger = logging.getLogger(__name__)

_IDENTIFYING_RESOURCE_KEYS = (
    "service.name",
    "service.namespace",
    "service.instance.id",
    "service.version",
)

_NON_IDENTIFYING_RESOURCE_KEYS = (
    "os.type",
    "os.name",
    "os.version",
    "host.name",
    "host.arch",
    "process.pid",
    "process.runtime.name",
    "process.runtime.version",
    # Note: deployment.environment.name may need to move: splunk-otel-java puts this in identifying
    "deployment.environment.name",
)

_DEFAULT_POLLING_INTERVAL_MS = 30000


def _start_opamp_if_enabled(resource_attrs, registry: ConfigRegistry, env: Env) -> None:
    if not env.is_true(SPLUNK_OPAMP_ENABLED):
        logger.debug("OpAMP disabled (SPLUNK_OPAMP_ENABLED not set to true)")
        return

    endpoint = env.getval(SPLUNK_OPAMP_ENDPOINT)
    if not endpoint:
        logger.warning("SPLUNK_OPAMP_ENABLED=true but SPLUNK_OPAMP_ENDPOINT is not set; OpAMP disabled")
        return

    token = env.getval(SPLUNK_OPAMP_TOKEN) or env.getval(SPLUNK_ACCESS_TOKEN)
    polling_interval_ms = env.getint(SPLUNK_OPAMP_POLLING_INTERVAL, _DEFAULT_POLLING_INTERVAL_MS)

    logger.info("Starting OpAMP client: %s", endpoint)

    try:
        _start_opamp(endpoint, token, polling_interval_ms, registry, resource_attrs)

    except Exception:
        logger.exception("Failed to start OpAMP client")


def _start_opamp(endpoint: str, token: str, polling_interval_ms: int, registry: ConfigRegistry, resource_attrs):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    identifying_attrs, non_identifying_attrs = _build_agent_attributes(resource_attrs)
    client = OpAMPClient(
        endpoint=endpoint,
        headers=headers,
        agent_identifying_attributes=identifying_attrs,
        agent_non_identifying_attributes=non_identifying_attrs,
    )
    client.update_effective_config(
        {"": registry.get_all()},
        content_type="application/json",
    )
    agent = OpAMPAgent(
        interval=polling_interval_ms / 1000,
        message_handler=_handle_server_message,
        client=client,
    )
    agent.start()
    logger.info("OpAMP client started")


def _build_agent_attributes(resource_attrs) -> tuple[dict, dict]:
    from splunk_otel.__about__ import __version__ as distro_version

    identifying_attrs = {}
    for key in _IDENTIFYING_RESOURCE_KEYS:
        val = resource_attrs.get(key)
        if val is not None:
            identifying_attrs[key] = str(val)

    identifying_attrs.update(
        {
            TELEMETRY_SDK_LANGUAGE: "python",
            TELEMETRY_SDK_NAME: "opentelemetry",
            TELEMETRY_SDK_VERSION: str(resource_attrs.get(TELEMETRY_SDK_VERSION, "unknown")),
            "telemetry.distro.name": _DISTRO_NAME,
            "telemetry.distro.version": distro_version,
        }
    )

    non_identifying_attrs = {}
    for key in _NON_IDENTIFYING_RESOURCE_KEYS:
        val = resource_attrs.get(key)
        if val is not None:
            non_identifying_attrs[key] = str(val)

    return identifying_attrs, non_identifying_attrs


def _handle_server_message(
    _agent: OpAMPAgent,
    _client: OpAMPClient,
    message: opamp_pb2.ServerToAgent,
) -> None:
    logger.debug("ServerToAgent: flags=%s", message.flags)
