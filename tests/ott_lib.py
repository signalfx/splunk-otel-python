import time
from pathlib import Path

from opentelemetry import trace

UPSTREAM_PRERELEASE_VERSION = "0.56b0"


def project_path():
    return str(Path(__file__).parent.parent)


def trace_loop(loops):
    tracer = trace.get_tracer("my-tracer")
    for _ in range(loops):
        with tracer.start_as_current_span("my-span"):
            time.sleep(0.5)
