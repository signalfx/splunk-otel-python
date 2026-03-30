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
from opentelemetry._opamp.callbacks import Callbacks, MessageData
from opentelemetry._opamp.client import OpAMPClient

from splunk_otel.env import (
    Env,
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_OPAMP_ENABLED,
    SPLUNK_OPAMP_ENDPOINT,
    SPLUNK_OPAMP_POLLING_INTERVAL,
    SPLUNK_OPAMP_TOKEN,
)

if TYPE_CHECKING:
    from splunk_otel.opamp.config_registry import ConfigRegistry

logger = logging.getLogger(__name__)

_DEFAULT_POLLING_INTERVAL_MS = 30000


# ---------------------------------------------------------------------------
# Config: pure data extracted from env vars
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpAMPConfig:
    endpoint: str
    token: str
    polling_interval_ms: int

    @classmethod
    def from_env(cls, env: Env) -> OpAMPConfig | None:
        if not env.is_true(SPLUNK_OPAMP_ENABLED):
            logger.debug("OpAMP disabled (SPLUNK_OPAMP_ENABLED not set to true)")
            return None

        endpoint = env.getval(SPLUNK_OPAMP_ENDPOINT)
        if not endpoint:
            logger.warning("SPLUNK_OPAMP_ENABLED=true but SPLUNK_OPAMP_ENDPOINT is not set; OpAMP disabled")
            return None

        token = env.getval(SPLUNK_OPAMP_TOKEN) or env.getval(SPLUNK_ACCESS_TOKEN)
        polling_interval_ms = env.getint(SPLUNK_OPAMP_POLLING_INTERVAL, _DEFAULT_POLLING_INTERVAL_MS)

        return cls(endpoint=endpoint, token=token, polling_interval_ms=polling_interval_ms)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class _SplunkCallbacks(Callbacks):
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
        logger.debug("ServerToAgent message received: remote_config=%s", message.remote_config is not None)


# ---------------------------------------------------------------------------
# Entry point (called from SplunkConfigurator)
# ---------------------------------------------------------------------------


def _start_opamp_if_enabled(
    resource_attrs,
    registry: ConfigRegistry,
    env: Env,
    client_factory=OpAMPClient,
    agent_factory=OpAMPAgent,
) -> OpAMPAgent | None:
    config = OpAMPConfig.from_env(env)
    if config is None:
        return None

    try:
        client = _build_client(config, resource_attrs, client_factory=client_factory)
        return _start_opamp(config, registry, client, agent_factory=agent_factory)
    except Exception:
        logger.exception("Failed to start OpAMP client")
        return None


def _start_opamp(config, registry, client, agent_factory=OpAMPAgent):
    client.update_effective_config(
        {"": registry.get_all()},
        content_type="application/json",
    )
    agent = agent_factory(
        interval=config.polling_interval_ms / 1000,
        callbacks=_SplunkCallbacks(),
        client=client,
    )
    agent.start()
    logger.info("OpAMP client started: %s", config.endpoint)
    return agent


def _build_client(config: OpAMPConfig, resource_attrs, client_factory=OpAMPClient):
    headers = {}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"

    identifying = {str(k): str(v) for k, v in resource_attrs.items()}

    return client_factory(
        endpoint=config.endpoint,
        headers=headers,
        agent_identifying_attributes=identifying,
        agent_non_identifying_attributes={},
    )
