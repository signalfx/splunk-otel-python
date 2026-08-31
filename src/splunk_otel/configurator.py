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

from opentelemetry.configuration import load_config_file
from opentelemetry.configuration._logger_provider import configure_logger_provider
from opentelemetry.configuration._meter_provider import configure_meter_provider
from opentelemetry.configuration._propagator import configure_propagator
from opentelemetry.configuration._resource import create_resource
from opentelemetry.configuration._tracer_provider import configure_tracer_provider
from opentelemetry.configuration.instrumentation import configure_instrumentation
from opentelemetry.configuration.models import OpenTelemetryConfiguration, Resource as ResourceConfig
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.sdk._configuration import _OTelSDKConfigurator
from opentelemetry.sdk.environment_variables import OTEL_CONFIG_FILE
from opentelemetry.sdk.resources import Resource

from splunk_otel.__about__ import __version__ as version
from splunk_otel.callgraphs import _configure_callgraphs_if_enabled
from splunk_otel.distro import _DEFAULT_SERVICE_NAME, _DISTRO_NAME
from splunk_otel.env import SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, Env
from splunk_otel.profile import _start_profiling_if_enabled
from splunk_otel.propagator import ServerTimingResponsePropagator
from splunk_otel.runtime import (
    _SERVER_TIMING_DEFAULT_ENABLED,
    configure_logging_instrumentation,
)

_logger = logging.getLogger(__name__)

_DECLARATIVE_SERVICE_NAME_WARNING = """The service.name attribute is not set, which may make your service difficult to identify.
Set your service name in the resource.attributes section of the OpenTelemetry configuration file."""


class SplunkConfigurator(_OTelSDKConfigurator):
    def _configure(self, **kwargs):
        env = Env()
        config_file = env.getval(OTEL_CONFIG_FILE)
        if config_file:
            config = _configure_declarative_sdk(config_file, **kwargs)
            if config is None:
                return
            server_timing_enabled = _declarative_server_timing_enabled(config)
        else:
            # use the env var configuration logic from the upstream configurator
            super()._configure(**kwargs)
            server_timing_enabled = env.is_true(
                SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
                str(_SERVER_TIMING_DEFAULT_ENABLED),
            )

        if server_timing_enabled:
            set_global_response_propagator(ServerTimingResponsePropagator())
        configure_logging_instrumentation(env)

        # A later change will configure profiling and callgraphs from OTEL_CONFIG_FILE.
        # For now, start them from environment variables only when no config file is set.
        if not config_file:
            _start_profiling_if_enabled()
            _configure_callgraphs_if_enabled()


def _configure_declarative_sdk(config_file: str, **kwargs) -> OpenTelemetryConfiguration | None:
    if kwargs:
        _logger.warning(
            "%s is set; ignoring configurator kwargs: %s",
            OTEL_CONFIG_FILE,
            sorted(kwargs),
        )

    config = load_config_file(config_file)
    if config.disabled:
        _logger.warning("Declarative configuration has disabled=true; skipping SDK setup.")
        return None

    resource = _create_declarative_resource(config.resource)
    configure_tracer_provider(config.tracer_provider, resource)
    configure_meter_provider(config.meter_provider, resource)
    configure_logger_provider(config.logger_provider, resource)
    configure_propagator(config.propagator)
    configure_instrumentation(config.instrumentation_development)
    return config


def _declarative_server_timing_enabled(config: OpenTelemetryConfiguration) -> bool:
    match config.distribution:
        case {
            "splunk": {
                "instrumentations": {
                    "http": {
                        "trace_response_header_enabled": bool(enabled),
                    },
                },
            },
        }:
            return enabled
        case _:
            return _SERVER_TIMING_DEFAULT_ENABLED


def _create_declarative_resource(resource_config: ResourceConfig | None) -> Resource:
    resource = create_resource(resource_config)
    attributes = {
        "telemetry.distro.name": _DISTRO_NAME,
        "telemetry.distro.version": version,
    }
    service_name = resource.attributes.get("service.name")
    if not service_name or str(service_name).startswith("unknown_service"):
        _logger.warning(_DECLARATIVE_SERVICE_NAME_WARNING)
        attributes["service.name"] = _DEFAULT_SERVICE_NAME
    return resource.merge(Resource(attributes))
