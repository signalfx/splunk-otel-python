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
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

from splunk_otel.env import DEFAULTS, Env, OTEL_METRICS_ENABLED


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

    def set_env_defaults(self):
        for key, value in DEFAULTS.items():
            self.env.setdefault(key, value)

    def load_instrumentor(self, entry_point, **kwargs):
        #  This method is called in a loop by opentelemetry-instrumentation
        if is_system_metrics_instrumentor(entry_point) and not self.env.is_true(
            OTEL_METRICS_ENABLED
        ):
            self.logger.info(
                f"{OTEL_METRICS_ENABLED} not set -- skipping SystemMetricsInstrumentor"
            )
        else:
            super().load_instrumentor(entry_point, **kwargs)


def is_system_metrics_instrumentor(entry_point):
    if entry_point.name == "system_metrics":
        instrumentor_class = entry_point.load()
        if instrumentor_class == SystemMetricsInstrumentor:
            return True
    return False
