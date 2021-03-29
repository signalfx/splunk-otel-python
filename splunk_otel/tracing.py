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

from opentelemetry import environment_variables as otel_env_vars
from opentelemetry import propagate, trace
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


def start_tracing(*args, **kwargs):
    enabled = os.environ.get("OTEL_TRACE_ENABLED", True)
    if not _is_truthy(enabled):
        logger.info("tracing has been disabled with OTEL_TRACE_ENABLED=%s", enabled)
        return

    options = Options(*args, **kwargs)
    try:
        _configure_tracing(options)
        _load_instrumentors()
    except Exception:  # pylint:disable=broad-except
        sys.exit(2)


def _configure_tracing(options: Options):
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
    exporter_options = {
        "collector_endpoint": options.endpoint,
        "max_tag_value_length": options.max_attr_length,
    }

    if options.access_token:
        exporter_options.update(
            {
                "username": "auth",
                "password": options.access_token,
            }
        )

    return JaegerExporter(**exporter_options)


def _load_instrumentors():
    package_to_exclude = os.environ.get(
        otel_env_vars.OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, []
    )
    if isinstance(package_to_exclude, str):
        package_to_exclude = package_to_exclude.split(",")
        # to handle users entering "requests , flask" or "requests, flask" with spaces
        package_to_exclude = [x.strip() for x in package_to_exclude]

    for entry_point in iter_entry_points("opentelemetry_instrumentor"):
        try:
            if entry_point.name in package_to_exclude:
                logger.debug("Instrumentation skipped for library %s", entry_point.name)
                continue
            entry_point.load()().instrument()  # type: ignore
            logger.debug("Instrumented %s", entry_point.name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Instrumenting of %s failed", entry_point.name)
            raise exc


def _is_truthy(value: any) -> bool:
    if isinstance(value, str):
        value = value.lower()
    return value in [True, 1, "true", "yes"]
