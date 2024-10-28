import time
from pathlib import Path

from opentelemetry import trace
from oteltest.telemetry import num_spans

NUM_SPANS = 12


def trace_loop(loops):
    tracer = trace.get_tracer("my-tracer")
    for _ in range(loops):
        with tracer.start_as_current_span("my-span"):
            time.sleep(0.5)


if __name__ == "__main__":
    trace_loop(NUM_SPANS)


class MyOtelTest:
    def requirements(self):
        parent_dir = str(Path(__file__).parent.parent)
        return parent_dir, "oteltest"

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-svc",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:  # noqa: ARG002
        span_count = num_spans(telemetry)
        assert span_count == NUM_SPANS

    def is_http(self):
        return False
