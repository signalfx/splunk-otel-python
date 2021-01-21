import logging
import os
import sys
from typing import Optional

from opentelemetry import propagators, trace
from opentelemetry.exporter.jaeger import JaegerSpanExporter
from opentelemetry.propagators.b3 import B3Format
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchExportSpanProcessor
from pkg_resources import iter_entry_points

from splunk_otel.excludes import excluded_instrumentations
from splunk_otel.version import __version__

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

DEFAULT_SERVICE_NAME = "unnamed-python-service"
DEFAULT_ENDPOINT = "http://localhost:9080/v1/trace"
DEFAULT_MAX_ATTR_LENGTH = 1200


propagators.set_global_textmap(B3Format())


def start_tracing(url: str = None, service_name: str = None):
    try:
        enabled = os.environ.get("OTEL_TRACE_ENABLED", True)
        if not _is_truthy(enabled):
            logger.info("tracing has been disabled with OTEL_TRACE_ENABLED=%s", enabled)
            return

        init_tracer(url, service_name)
        auto_instrument()
    except Exception:  # pylint:disable=broad-except
        sys.exit(2)


def init_tracer(url=None, service_name=None):
    if not url:
        url = os.environ.get(
            "SPLK_TRACE_EXPORTER_URL",
            DEFAULT_ENDPOINT,
        )

    if not service_name:
        service_name = os.environ.get(
            "SPLK_SERVICE_NAME",
            DEFAULT_SERVICE_NAME,
        )

    access_token = os.environ.get("SPLK_ACCESS_TOKEN", None)

    provider = TracerProvider(
        resource=Resource.create(
            attributes={
                "service.name": service_name,
                "telemetry.auto.version": __version__,
            }
        )
    )
    trace.set_tracer_provider(provider)
    exporter = new_exporter(url, service_name, access_token)
    provider.add_span_processor(BatchExportSpanProcessor(exporter))


def new_exporter(
    url: str, service_name: str, access_token: Optional[str] = None
) -> JaegerSpanExporter:
    exporter_options = {
        "service_name": service_name,
        "collector_endpoint": url,
    }

    if access_token:
        exporter_options.update(
            {
                "username": "auth",
                "password": access_token,
            }
        )

    return JaegerSpanExporter(**exporter_options)


def auto_instrument():
    for entry_point in iter_entry_points("opentelemetry_instrumentor"):
        if entry_point.name in excluded_instrumentations:
            logger.info(
                "%s instrumentation has been temporarily disabled by Splunk",
                entry_point.name,
            )
            continue

        try:
            entry_point.load()().instrument()  # type: ignore
            logger.debug(
                "Instrumented %s",
                entry_point.name,
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Instrumenting of %s failed",
                entry_point.name,
            )


def _is_truthy(value: any) -> bool:
    if isinstance(value, str):
        value = value.lower()
    return value in [True, 1, "true", "yes"]
