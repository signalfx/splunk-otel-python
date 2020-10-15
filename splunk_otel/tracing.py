import os
import sys
import logging

from opentelemetry import trace
from opentelemetry.exporter.zipkin import ZipkinSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchExportSpanProcessor
from opentelemetry import propagators
from opentelemetry.sdk.trace.propagation.b3_format import B3Format
from pkg_resources import iter_entry_points

from splunk_otel.excludes import excluded_instrumentations

# TODO: add support for debug logging
# logging.basicConfig(level=logging.ERROR)

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

DEFAULT_SERVICE_NAME = "unnamed-python-service"
DEFAULT_ENDPOINT = "http://localhost:9080/v1/trace"
DEFAULT_MAX_ATTR_LENGTH = 1200


# auto-enable django instrumentation. remove after this is fixed upstream
os.environ['OTEL_PYTHON_DJANGO_INSTRUMENT'] = 'True'

propagators.set_global_textmap(B3Format())


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

    exporter = ZipkinSpanExporter(
        url=url,
        service_name=service_name,
        max_tag_value_length=int(
            os.environ.get("SPLK_MAX_ATTR_LENGTH", DEFAULT_MAX_ATTR_LENGTH)
        ),
    )
    provider.add_span_processor(BatchExportSpanProcessor(exporter))


def auto_instrument():
    for entry_point in iter_entry_points("opentelemetry_instrumentor"):
        if entry_point.name in excluded_instrumentations:
            logger.info("%s instrumentation has been temporarily disabled by Splunk", entry_point.name)
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
