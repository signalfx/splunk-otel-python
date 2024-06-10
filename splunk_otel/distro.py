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
import os
from typing import Any, Dict

from opentelemetry.instrumentation.distro import BaseDistro  # type: ignore
from opentelemetry.sdk._configuration import _OTelSDKConfigurator
from opentelemetry.sdk.environment_variables import (
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
)

from splunk_otel.options import _Options
from splunk_otel.profiling import start_profiling
from splunk_otel.profiling.options import _Options as ProfilingOptions
from splunk_otel.symbols import (
    _DEFAULT_MAX_ATTR_LENGTH,
    _DEFAULT_SPAN_LINK_COUNT_LIMIT,
    _SPLUNK_DISTRO_VERSION_ATTR,
)
from splunk_otel.util import _is_truthy
from splunk_otel.version import __version__

logger = logging.getLogger(__name__)


class SplunkConfigurator(_OTelSDKConfigurator):
    pass


class _SplunkDistro(BaseDistro):
    def __init__(self):
        profiling_enabled = os.environ.get("SPLUNK_PROFILER_ENABLED", False)
        self._profiling_enabled = _is_truthy(profiling_enabled)

    def _configure_access_token(self) -> None:
        if "SPLUNK_ACCESS_TOKEN" in os.environ:
            access_token = os.environ["SPLUNK_ACCESS_TOKEN"]
            if access_token == "":
                return
            headers = ""
            if "OTEL_EXPORTER_OTLP_HEADERS" in os.environ:
                headers = os.environ["OTEL_EXPORTER_OTLP_HEADERS"] + ","
            headers += "x-sf-token=" + access_token
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = headers

    def _configure_resource_attributes(self) -> None:
        resource_attributes = ""
        if "OTEL_RESOURCE_ATTRIBUTES" in os.environ:
            resource_attributes = os.environ["OTEL_RESOURCE_ATTRIBUTES"] + ","
        resource_attributes += _SPLUNK_DISTRO_VERSION_ATTR + "=" + __version__
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = resource_attributes

    def _set_default_env(self) -> None:
        defaults = {
            OTEL_SPAN_LINK_COUNT_LIMIT: str(_DEFAULT_SPAN_LINK_COUNT_LIMIT),
            OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: str(_DEFAULT_MAX_ATTR_LENGTH),
        }
        for key, value in defaults.items():
            if key not in os.environ:
                os.environ[key] = value

    def _configure(self, **kwargs: Dict[str, Any]) -> None:
        self._set_default_env()
        self._configure_access_token()
        self._configure_resource_attributes()

        if self._profiling_enabled:
            start_profiling()
