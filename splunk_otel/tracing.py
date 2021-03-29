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
from functools import partial
from typing import Any, Optional

from opentelemetry import environment_variables as otel_env_vars
from opentelemetry import propagate, trace  # type: ignore
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.propagators.b3 import B3Format
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pkg_resources import iter_entry_points

from splunk_otel.options import Options
from splunk_otel.version import __version__

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

propagate.set_global_textmap(B3Format())


def start_tracing(
    service_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    access_token: Optional[str] = None,
    max_attr_length: Optional[int] = None,
) -> None:
    enabled = os.environ.get("OTEL_TRACE_ENABLED", True)
    if not _is_truthy(enabled):
        logger.info("tracing has been disabled with OTEL_TRACE_ENABLED=%s", enabled)
        return

    options = Options(service_name, endpoint, access_token, max_attr_length)
    try:
        _configure_tracing(options)
        _load_instrumentors()
    except Exception:  # pylint:disable=broad-except
        sys.exit(2)


def _configure_tracing(options: Options) -> None:
    provider = TracerProvider(
        resource=Resource.create(
            attributes={
                "service.name": options.service_name,
                "telemetry.auto.version": __version__,
            }
        )
    )
    trace.set_tracer_provider(provider)
    exporter = _new_jaeger_exporter(options)
    provider.add_span_processor(BatchSpanProcessor(exporter))


def _new_jaeger_exporter(options: Options) -> JaegerExporter:
    exporter_factory = partial(
        JaegerExporter,
        collector_endpoint=options.endpoint,
        max_tag_value_length=options.max_attr_length,
    )

    if options.access_token:
        return exporter_factory(username="auth", password=options.access_token)
    return exporter_factory()


def _load_instrumentors() -> None:
    package_to_exclude = os.environ.get(
        otel_env_vars.OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, ""
    ).split(",")
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


def _is_truthy(value: Any) -> bool:
    if isinstance(value, str):
        value = value.lower().strip()
    return value in [True, 1, "true", "yes"]
