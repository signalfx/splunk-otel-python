import logging
from pathlib import Path

from opentelemetry import _logs, metrics, trace
from opentelemetry.propagate import get_global_textmap

from lib import project_path

LOGGER_NAME = "declarative-test"
LOG_MESSAGE = "declarative configuration test"
METRIC_NAME = "declarative.test"
SERVICE_NAME = "declarative-test"
SPAN_NAME = "declarative-test-span"


if __name__ == "__main__":
    from opentelemetry.instrumentation.propagators import get_global_response_propagator

    logging.basicConfig(level=logging.INFO)

    tracer = trace.get_tracer("declarative-test")
    meter = metrics.get_meter("declarative-test")
    logger = logging.getLogger(LOGGER_NAME)

    with tracer.start_as_current_span(SPAN_NAME):
        meter.create_counter(METRIC_NAME).add(1)
        logger.warning(LOG_MESSAGE)

    trace.get_tracer_provider().force_flush()
    metrics.get_meter_provider().force_flush()
    _logs.get_logger_provider().force_flush()
    print(type(get_global_textmap()).__name__)  # noqa: T201
    print(f"response-propagator={type(get_global_response_propagator()).__name__}")  # noqa: T201


class DeclarativeConfigOtelTest:
    def requirements(self):
        return (project_path(),)

    def declarative_configuration(self):
        config = Path(project_path(), "docs", "examples", "declarative-config.yaml").read_text()
        return (
            config
            + """
distribution:
  splunk:
    instrumentations:
      http:
        trace_response_header_enabled: false
"""
        )

    def environment_variables(self):
        return {
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
            "OTEL_SERVICE_NAME": SERVICE_NAME,
            "SPLUNK_TRACE_RESPONSE_HEADER_ENABLED": "true",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import (
            extract_leaves,
            get_attribute,
            get_logs,
            get_metric_names,
            get_span_names,
        )

        assert returncode == 0, stderr
        assert SPAN_NAME in get_span_names(telemetry)
        assert METRIC_NAME in get_metric_names(telemetry)
        assert any(record.body.string_value == LOG_MESSAGE for record in get_logs(telemetry))
        assert "CompositePropagator" in stdout
        assert "response-propagator=NoneType" in stdout

        attributes = extract_leaves(
            telemetry,
            "trace_requests",
            "pbreq",
            "resource_spans",
            "resource",
            "attributes",
        )
        assert get_attribute(attributes, "service.name").value.string_value == SERVICE_NAME
        assert get_attribute(attributes, "telemetry.distro.name").value.string_value == "splunk-opentelemetry"

    def is_http(self):
        return False
