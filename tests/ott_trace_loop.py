from oteltest.telemetry import num_spans
from ott_lib import project_path, trace_loop

NUM_SPANS = 12

if __name__ == "__main__":
    trace_loop(NUM_SPANS)


class NumSpansOtelTest:
    def requirements(self):
        return project_path(), "oteltest"

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-svc",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:  # noqa: ARG002
        assert num_spans(telemetry) == NUM_SPANS

    def is_http(self):
        return False