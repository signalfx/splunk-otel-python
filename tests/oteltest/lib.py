import time

from opentelemetry import trace


def trace_loop():
    tracer = trace.get_tracer('oteltest')
    for i in range(16):
        with tracer.start_as_current_span(f"loop-{i}"):
            print(i)
            time.sleep(1)
