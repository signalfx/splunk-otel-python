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
from typing import Collection, Dict, Optional, Union

from opentelemetry import trace
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS,
)
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pkg_resources import iter_entry_points

from splunk_otel.options import _Options, _SpanExporterFactory
from splunk_otel.util import _is_truthy

logger = logging.getLogger(__name__)


def start_tracing(
    service_name: Optional[str] = None,
    span_exporter_factories: Optional[Collection[_SpanExporterFactory]] = None,
    access_token: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    trace_response_header_enabled: Optional[bool] = None,
) -> trace.TracerProvider:
    enabled = os.environ.get("OTEL_TRACE_ENABLED", True)
    if not _is_truthy(enabled):
        logger.info("tracing has been disabled with OTEL_TRACE_ENABLED=%s", enabled)
        return None

    options = _Options(
        service_name,
        span_exporter_factories,
        access_token,
        resource_attributes,
        trace_response_header_enabled,
    )
    try:
        provider = _configure_tracing(options)
        _load_instrumentors()
        return provider
    except Exception as error:  # pylint:disable=broad-except
        logger.error("tracing could not be enabled: %s", error)
        return trace.NoOpTracerProvider()


def _configure_tracing(options: _Options) -> TracerProvider:
    provider = TracerProvider(resource=options.resource)
    set_global_response_propagator(options.response_propagator)  # type: ignore
    trace.set_tracer_provider(provider)
    for factory in options.span_exporter_factories:
        provider.add_span_processor(BatchSpanProcessor(factory(options)))
    return provider


def _load_instrumentors() -> None:
    package_to_exclude = os.environ.get(OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, "").split(
        ","
    )
    package_to_exclude = [p.strip() for p in package_to_exclude]

    for entry_point in iter_entry_points("opentelemetry_instrumentor"):
        try:
            if entry_point.name in package_to_exclude:
                logger.debug("Instrumentation skipped for library %s", entry_point.name)
                continue
            entry_point.load()().instrument()
            logger.debug("Instrumented %s", entry_point.name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Instrumenting of %s failed", entry_point.name)
            raise exc
