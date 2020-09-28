import os
import sys
from logging import getLogger

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchExportSpanProcessor
from pkg_resources import iter_entry_points

from splunk_otel.exporter.zipkin import ZipkinSpanExporter

logger = getLogger(__file__)

DEFAULT_SERVICE_NAME = "unnamed-python-service"
DEFAULT_ENDPOINT = "http://localhost:9080/v1/trace"


def start_tracing(url=None, service_name=None):
    init_tracer(url, service_name)
    auto_instrument()


def init_tracer(url=None, service_name=None):
    if not url:
        url = os.environ.get(
            "OTEL_EXPORTER_ZIPKIN_ENDPOINT",
            DEFAULT_ENDPOINT,
        )

    if not service_name:
        service_name = os.environ.get(
            "SPLK_SERVICE_NAME",
            DEFAULT_SERVICE_NAME,
        )

    provider = TracerProvider(
        resource=Resource.create(
            attributes={
                "service.name": service_name,
            }
        )
    )
    trace.set_tracer_provider(provider)

    exporter = ZipkinSpanExporter(url=url, service_name=service_name)
    provider.add_span_processor(BatchExportSpanProcessor(exporter))


def auto_instrument():
    for entry_point in iter_entry_points("opentelemetry_instrumentor"):
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
