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

from splunk_otel.options import _Options
from splunk_otel.profiling import _start_profiling
from splunk_otel.profiling.options import _Options as ProfilingOptions
from splunk_otel.symbols import _SPLUNK_DISTRO_VERSION_ATTR
from splunk_otel.util import _is_truthy
from splunk_otel.version import __version__

logger = logging.getLogger(__name__)


class SplunkConfigurator(_OTelSDKConfigurator):
    pass


class _SplunkDistro(BaseDistro):
    def __init__(self):
        profiling_enabled = os.environ.get("SPLUNK_PROFILER_ENABLED", False)
        self._profiling_enabled = _is_truthy(profiling_enabled)

    def configure_access_token(self):
        if "SPLUNK_ACCESS_TOKEN" in os.environ:
            access_token = os.environ["SPLUNK_ACCESS_TOKEN"]
            if access_token == "":
                return
            headers = ""
            if "OTEL_EXPORTER_OTLP_HEADERS" in os.environ:
                headers = os.environ["OTEL_EXPORTER_OTLP_HEADERS"] + ","
            headers += "x-sf-token=" + access_token
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = headers

    def configure_resource_attributes(self):
        resource_attributes = ""
        if "OTEL_RESOURCE_ATTRIBUTES" in os.environ:
            resource_attributes = os.environ["OTEL_RESOURCE_ATTRIBUTES"] + ","
        resource_attributes += _SPLUNK_DISTRO_VERSION_ATTR + "=" + __version__
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = resource_attributes

    def _configure(self, **kwargs: Dict[str, Any]) -> None:
        self.configure_access_token()
        self.configure_resource_attributes()
        # FIXME the Options construtor side effect could live here?
        _Options()

        if self._profiling_enabled:
            _start_profiling(ProfilingOptions())
