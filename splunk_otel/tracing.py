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
import sys
from typing import Collection, Dict, Optional, Union

from opentelemetry import trace
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS,
)
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pkg_resources import iter_entry_points

from splunk_otel.env import _EnvLoaderABC, _OSEnvLoader
from splunk_otel.options import _Options, _SpanExporterFactory, _set_default_env
from splunk_otel.util import _is_truthy

logger = logging.getLogger(__name__)


def start_tracing(
    service_name: Optional[str] = None,
    span_exporter_factories: Optional[Collection[_SpanExporterFactory]] = None,
    access_token: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    trace_response_header_enabled: Optional[bool] = None,
) -> TracerProvider:
    return _do_start_tracing(
        _OSEnvLoader(),
        service_name,
        span_exporter_factories,
        access_token,
        resource_attributes,
        trace_response_header_enabled,
    )


def _do_start_tracing(
    env_loader: _EnvLoaderABC,
    service_name: Optional[str] = None,
    span_exporter_factories: Optional[Collection[_SpanExporterFactory]] = None,
    access_token: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    trace_response_header_enabled: Optional[bool] = None,
) -> TracerProvider:
    enabled = env_loader.get("OTEL_TRACE_ENABLED", True)
    if not _is_truthy(enabled):
        logger.info("tracing has been disabled with OTEL_TRACE_ENABLED=%s", enabled)
        return None

    options = _Options(
        service_name,
        span_exporter_factories,
        access_token,
        resource_attributes,
        trace_response_header_enabled,
        env_loader,
    )
    try:
        provider = _configure_tracing(options, env_loader)
        _load_instrumentors(env_loader)
        return provider
    except Exception:  # pylint:disable=broad-except
        sys.exit(2)


def _configure_tracing(options: _Options, env_loader: _EnvLoaderABC) -> TracerProvider:
    _set_default_env(env_loader)

    provider = TracerProvider(resource=options.resource)
    set_global_response_propagator(options.response_propagator)  # type: ignore
    trace.set_tracer_provider(provider)
    for factory in options.span_exporter_factories:
        exporter = factory(options)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def _load_instrumentors(env: _EnvLoaderABC) -> None:
    disabled_instrumentations = env.get(OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, "")
    package_to_exclude = disabled_instrumentations.split(",")
    package_to_exclude = [p.strip() for p in package_to_exclude]

    for entry_point in iter_entry_points("opentelemetry_instrumentor"):
        try:
            if entry_point.name in package_to_exclude:
                logger.debug("Instrumentation skipped for library %s", entry_point.name)
                continue
            instrumentor_class = entry_point.load()
            instrumentor_class().instrument()
            logger.debug("Instrumented %s", entry_point.name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Instrumenting of %s failed", entry_point.name)
            raise exc
