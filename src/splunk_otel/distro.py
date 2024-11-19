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
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_HEADERS

from splunk_otel.env import (
    DEFAULTS,
    OTEL_LOGS_ENABLED,
    OTEL_METRICS_ENABLED,
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED,
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
    X_SF_TOKEN,
    Env,
)
from splunk_otel.propagator import ServerTimingResponsePropagator


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
        self.set_profiling_env()
        self.configure_headers()
        self.set_server_timing_propagator()

    def set_env_defaults(self):
        for key, value in DEFAULTS.items():
            self.env.setdefault(key, value)

    def set_profiling_env(self):
        if self.env.is_true(SPLUNK_PROFILER_ENABLED, "false"):
            self.env.setdefault(OTEL_LOGS_ENABLED, "true")
            self.env.setdefault(OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED, "true")

    def configure_headers(self):
        tok = self.env.getval(SPLUNK_ACCESS_TOKEN).strip()
        if tok:
            self.env.list_append(OTEL_EXPORTER_OTLP_HEADERS, f"{X_SF_TOKEN}={tok}")

    def load_instrumentor(self, entry_point, **kwargs):
        #  This method is called in a loop by opentelemetry-instrumentation
        if is_system_metrics_instrumentor(entry_point) and not self.env.is_true(OTEL_METRICS_ENABLED):
            self.logger.info("%s not set -- skipping SystemMetricsInstrumentor", OTEL_METRICS_ENABLED)
        else:
            super().load_instrumentor(entry_point, **kwargs)

    def set_server_timing_propagator(self):
        if self.env.is_true(SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, "true"):
            set_global_response_propagator(ServerTimingResponsePropagator())


def is_system_metrics_instrumentor(entry_point):
    if entry_point.name == "system_metrics":
        instrumentor_class = entry_point.load()
        if instrumentor_class == SystemMetricsInstrumentor:
            return True
    return False
