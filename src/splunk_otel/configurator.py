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

from opentelemetry import trace
from opentelemetry.sdk._configuration import _OTelSDKConfigurator

from splunk_otel.profile import _start_profiling_if_enabled
from splunk_otel.callgraphs import _configure_callgraphs_if_enabled
from splunk_otel.opamp import _start_opamp_if_enabled
from splunk_otel.opamp.config_registry import ConfigRegistry
from splunk_otel.env import (
    Env,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
    OTEL_SERVICE_NAME,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
)


class SplunkConfigurator(_OTelSDKConfigurator):
    def _configure(self, **kwargs):
        super()._configure(**kwargs)

        env = Env()
        profiling = _start_profiling_if_enabled(env)
        callgraphs = _configure_callgraphs_if_enabled(env)

        opamp_registry = self._build_opamp_registry(profiling, callgraphs, env)
        resource = trace.get_tracer_provider().resource
        _start_opamp_if_enabled(resource.attributes, opamp_registry, env)

    def _build_opamp_registry(self, profiling_state, callgraphs_state, env) -> ConfigRegistry:
        registry = ConfigRegistry()
        registry.register(SPLUNK_PROFILER_ENABLED, getter=lambda: str(profiling_state.is_enabled()).lower())
        registry.register(SPLUNK_PROFILER_CALL_STACK_INTERVAL, getter=lambda: str(profiling_state.interval_millis()))
        registry.register(SPLUNK_SNAPSHOT_PROFILER_ENABLED, getter=lambda: str(callgraphs_state.is_enabled()).lower())
        registry.register(SPLUNK_SNAPSHOT_SAMPLING_INTERVAL, getter=lambda: str(callgraphs_state.interval()))

        for key in (
            OTEL_SERVICE_NAME,
            OTEL_EXPORTER_OTLP_ENDPOINT,
            OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
            OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
        ):
            registry.register(key, getter=lambda k=key: env.getval(k) or None)
        return registry
