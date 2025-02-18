import logging

from opentelemetry import trace
from ott_lib import UPSTREAM_PRERELEASE_VERSION, project_path

MESSAGE = "uh oh!"
LOGGER_NAME = "logging-ott"

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    tracer = trace.get_tracer(__file__)
    logger = logging.getLogger(LOGGER_NAME)
    with tracer.start_as_current_span("my-span"):
        logger.warning(MESSAGE)


class LoggingOtelTest:
    def requirements(self):
        return project_path(), f"opentelemetry-instrumentation-logging=={UPSTREAM_PRERELEASE_VERSION}"

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "mysvc",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return False

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        records = get_scope_log_records(telemetry, LOGGER_NAME)
        assert len(records) == 1
        record = records[0]
        assert record.body.string_value == MESSAGE
        assert record.trace_id


def get_scope_log_records(telemetry, scope_name):
    from oteltest.telemetry import extract_leaves

    out = []
    scope_logs = extract_leaves(telemetry, "log_requests", "pbreq", "resource_logs", "scope_logs")
    for scope_log in scope_logs:
        if scope_log.scope.name == scope_name:
            out.extend(scope_log.log_records)
    return out
