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
from typing import Optional

logger = logging.getLogger("options")


DEFAULT_SERVICE_NAME = "unnamed-python-service"
DEFAULT_ENDPOINT = "http://localhost:9080/v1/trace"
DEFAULT_MAX_ATTR_LENGTH = 1200


class Options:
    endpoint: str
    service_name: str
    access_token: str
    max_attr_length: int

    def __init__(
        self,
        service_name: str = None,
        endpoint: str = None,
        access_token: str = None,
        max_attr_length: int = None,
    ):
        if not endpoint:
            endpoint = environ.get("OTEL_EXPORTER_JAEGER_ENDPOINT", None)
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

        if not service_name:
            service_name = splunk_env_var("SERVICE_NAME", DEFAULT_ENDPOINT)
        self.service_name = service_name

        if not access_token:
            access_token = splunk_env_var("ACCESS_TOKEN", None)
        self.access_token = service_name

        if not max_attr_length:
            max_attr_length = splunk_env_var("MAX_ATTR_LENGTH", DEFAULT_MAX_ATTR_LENGTH)
        self.max_attr_length = max_attr_length


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
