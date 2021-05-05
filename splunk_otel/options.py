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
from os import environ
from typing import Dict, Optional, Union

from opentelemetry.sdk.environment_variables import OTEL_RESOURCE_ATTRIBUTES

from splunk_otel.version import __version__

logger = logging.getLogger("options")


DEFAULT_SERVICE_NAME = "unnamed-python-service"
DEFAULT_ENDPOINT = "http://localhost:9080/v1/trace"
DEFAULT_MAX_ATTR_LENGTH = 1200

_SERVICE_NAME_ATTR = "service.name"
_TELEMETRY_VERSION_ATTR = "telemetry.auto.version"
_NO_SERVICE_NAME_WARNING = """service.name attribute is not set, your service is unnamed and will be difficult to identify.
set your service name using the OTEL_RESOURCE_ATTRIBUTES environment variable.
E.g. `OTEL_RESOURCE_ATTRIBUTES="service.name=<YOUR_SERVICE_NAME_HERE>"`"""


class Options:
    endpoint: str
    access_token: Optional[str]
    max_attr_length: int
    resource_attributes: Dict[str, Union[str, bool, int, float]]
    response_propagation: bool

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_token: Optional[str] = None,
        max_attr_length: Optional[int] = None,
        resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
        trace_response_header_enabled: bool = True,
    ):
        if not endpoint:
            endpoint = environ.get("OTEL_EXPORTER_JAEGER_ENDPOINT")
            if not endpoint:
                endpoint = splunk_env_var("TRACE_EXPORTER_URL")
                if endpoint:
                    logger.warning(
                        "%s is deprecated and will be removed soon. Please use %s instead",
                        "SPLUNK_TRACE_EXPORTER_URL",
                        "OTEL_EXPORTER_JAEGER_ENDPOINT",
                    )
            endpoint = endpoint or DEFAULT_ENDPOINT
        self.endpoint = endpoint

        if not access_token:
            access_token = splunk_env_var("ACCESS_TOKEN")
        self.access_token = access_token or None

        if not max_attr_length:
            value = splunk_env_var("MAX_ATTR_LENGTH")
            if value:
                try:
                    max_attr_length = int(value)
                except (TypeError, ValueError):
                    logger.error("SPLUNK_MAX_ATTR_LENGTH must be a number.")
        self.max_attr_length = max_attr_length or DEFAULT_MAX_ATTR_LENGTH

        if not resource_attributes:
            resource_attributes = {}
            env_value = environ.get(OTEL_RESOURCE_ATTRIBUTES, "").strip()
            if env_value:
                resource_attributes = {
                    key.strip(): value.strip()
                    for key, value in (pair.split("=") for pair in env_value.split(","))
                }
        self.resource_attributes = resource_attributes or {}

        self.resource_attributes.update({_TELEMETRY_VERSION_ATTR: __version__})
        if _SERVICE_NAME_ATTR not in self.resource_attributes:
            logger.warning(_NO_SERVICE_NAME_WARNING)
            self.resource_attributes[_SERVICE_NAME_ATTR] = DEFAULT_SERVICE_NAME

        response_header_env = splunk_env_var("TRACE_RESPONSE_HEADER_ENABLED", "")
        if response_header_env and response_header_env.strip().lower() in (
            "false",
            "no",
            "f",
            "0",
        ):
            trace_response_header_enabled = False
        self.response_propagation = trace_response_header_enabled


def splunk_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    old_key = "SPLK_{0}".format(name)
    new_key = "SPLUNK_{0}".format(name)
    if old_key in environ:
        logger.warning(
            "%s is deprecated and will be removed soon. Please use %s instead",
            old_key,
            new_key,
        )
        return environ[old_key]
    return environ.get(new_key, default)
