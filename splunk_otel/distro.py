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

from opentelemetry.environment_variables import (
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.instrumentation.distro import BaseDistro  # type: ignore
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.sdk._configuration import _OTelSDKConfigurator
from opentelemetry.sdk.environment_variables import (
    OTEL_ATTRIBUTE_COUNT_LIMIT,
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
    OTEL_EXPORTER_OTLP_HEADERS, OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_LINK_ATTRIBUTE_COUNT_LIMIT,
    OTEL_RESOURCE_ATTRIBUTES, OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_EVENT_COUNT_LIMIT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
)

from splunk_otel.profiling import start_profiling
from splunk_otel.propagators import _ServerTimingResponsePropagator
from splunk_otel.util import _is_truthy, _is_truthy_str
from splunk_otel.version import __version__

DEFAULT_MAX_ATTR_LENGTH = 12000
DEFAULT_SPAN_LINK_COUNT_LIMIT = 1000
SPLUNK_DISTRO_VERSION_ATTR = "splunk.distro.version"

logger = logging.getLogger(__name__)


# The distro, configurators, and instrumentors that have been registered via entrypoints
# are loaded by opentelemetry-instrumentation (contrib) via sitecustomize.py:
#
#   distro = _load_distro()     # loads entrypoints "opentelemetry_distro"
#   distro.configure()          # calls _configure() below
#   _load_configurators()       # loads entrypoints "opentelemetry_configurator"
#   _load_instrumentors(distro) # loads entrypoints "opentelemetry_instrumentor"
class SplunkDistro(BaseDistro):
    """
    This class is referenced in the local pyproject.toml:

    [tool.poetry.plugins."opentelemetry_distro"]
    splunk_distro = "splunk_otel.distro:SplunkDistro"
    """

    def _configure(self, **kwargs):
        # runs *before* the configurator
        self._set_env()
        self._configure_headers()
        self._configure_resource_attributes()
        self._set_server_timing_propagator()

    def _set_env(self):
        os.environ.setdefault("OTEL_PYTHON_LOG_CORRELATION", "true")  # FIXME revisit
        os.environ.setdefault(OTEL_TRACES_EXPORTER, "otlp")
        os.environ.setdefault(OTEL_METRICS_EXPORTER, "otlp")
        os.environ.setdefault(OTEL_EXPORTER_OTLP_PROTOCOL, "grpc")  # FIXME revisit
        os.environ.setdefault(OTEL_ATTRIBUTE_COUNT_LIMIT, "")
        os.environ.setdefault(OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT, "")
        os.environ.setdefault(OTEL_SPAN_EVENT_COUNT_LIMIT, "")
        os.environ.setdefault(OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT, "")
        os.environ.setdefault(OTEL_LINK_ATTRIBUTE_COUNT_LIMIT, "")
        os.environ.setdefault(
            OTEL_SPAN_LINK_COUNT_LIMIT, str(DEFAULT_SPAN_LINK_COUNT_LIMIT)
        )
        os.environ.setdefault(
            OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT, str(DEFAULT_MAX_ATTR_LENGTH)
        )

    def _configure_headers(self) -> None:
        access_token = os.environ.get("SPLUNK_ACCESS_TOKEN", "")
        if access_token == "":
            return
        headers = ""
        if OTEL_EXPORTER_OTLP_HEADERS in os.environ:
            headers = os.environ[OTEL_EXPORTER_OTLP_HEADERS] + ","
        headers += "x-sf-token=" + access_token
        os.environ[OTEL_EXPORTER_OTLP_HEADERS] = headers

    def _configure_resource_attributes(self) -> None:
        resource_attributes = ""
        if OTEL_RESOURCE_ATTRIBUTES in os.environ:
            resource_attributes = os.environ[OTEL_RESOURCE_ATTRIBUTES] + ","
        resource_attributes += SPLUNK_DISTRO_VERSION_ATTR + "=" + __version__
        os.environ[OTEL_RESOURCE_ATTRIBUTES] = resource_attributes

    def _set_server_timing_propagator(self) -> None:
        if _is_truthy_str(os.environ.get("SPLUNK_TRACE_RESPONSE_HEADER_ENABLED", "true")):
            set_global_response_propagator(_ServerTimingResponsePropagator())


class SplunkConfigurator(_OTelSDKConfigurator):
    """
    The SDK configurator runs *after* the distro.

    This class is referenced in the local pyproject.toml:

    [tool.poetry.plugins."opentelemetry_configurator"]
    configurator = "splunk_otel.distro:SplunkConfigurator"
    """

    def _configure(self, **kwargs):
        super()._configure(**kwargs)
        if _is_truthy(os.environ.get("SPLUNK_PROFILER_ENABLED", False)):
            start_profiling()
