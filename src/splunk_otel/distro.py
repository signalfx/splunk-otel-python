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

import logging

from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_HEADERS,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)

from splunk_otel.__about__ import __version__ as version
from splunk_otel.env import (
    DEFAULTS,
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED,
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_PROFILER_LOGS_ENDPOINT,
    SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
    Env,
)
from splunk_otel.propagator import ServerTimingResponsePropagator

_DISTRO_NAME = "splunk-opentelemetry"

_NO_SERVICE_NAME_WARNING = """The service.name attribute is not set, which may make your service difficult to identify.
Set your service name using the OTEL_SERVICE_NAME environment variable.
e.g. `OTEL_SERVICE_NAME="<YOUR_SERVICE_NAME_HERE>"`"""
_DEFAULT_SERVICE_NAME = "unnamed-python-service"
_X_SF_TOKEN = "x-sf-token"  # noqa S105

_pylogger = logging.getLogger(__name__)


class SplunkDistro(BaseDistro):
    """
    Loaded by the opentelemetry-instrumentation package via an entrypoint when running `opentelemetry-instrument`
    """

    def __init__(self):
        # can't accept an arg here because of the parent class
        self.env = Env()
        self.logger = logging.getLogger(__name__)

    def _configure(self, **kwargs):
        self.set_env_defaults()
        self.check_service_name()
        self.set_profiling_env()
        self.set_resource_attributes()
        self.configure_headers()
        self.set_server_timing_propagator()

    def check_service_name(self):
        if not len(self.env.getval(OTEL_SERVICE_NAME)):
            _pylogger.warning(_NO_SERVICE_NAME_WARNING)
            self.env.setval(OTEL_SERVICE_NAME, _DEFAULT_SERVICE_NAME)

    def set_env_defaults(self):
        for key, value in DEFAULTS.items():
            self.env.setdefault(key, value)

    def set_profiling_env(self):
        if self.env.is_true(SPLUNK_PROFILER_ENABLED, "false"):
            self.env.setdefault(OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED, "true")
            logs_endpt = self.env.getval(SPLUNK_PROFILER_LOGS_ENDPOINT)
            if logs_endpt:
                self.env.setval(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, logs_endpt)

    def set_resource_attributes(self):
        self.env.list_append(OTEL_RESOURCE_ATTRIBUTES, f"telemetry.distro.name={_DISTRO_NAME}")
        self.env.list_append(OTEL_RESOURCE_ATTRIBUTES, f"telemetry.distro.version={version}")

    def configure_headers(self):
        tok = self.env.getval(SPLUNK_ACCESS_TOKEN).strip()
        if tok:
            self.env.list_append(OTEL_EXPORTER_OTLP_HEADERS, f"{_X_SF_TOKEN}={tok}")

    def set_server_timing_propagator(self):
        if self.env.is_true(SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, "true"):
            set_global_response_propagator(ServerTimingResponsePropagator())
