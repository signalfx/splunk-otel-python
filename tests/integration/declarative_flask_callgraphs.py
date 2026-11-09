import http.client
import json
import time
from threading import Event

from lib import project_path, wait_for_server

HOST = "127.0.0.1"
PORT = 8789
PARENT_SPAN_ID = "0123456789abcdef"
OFF_HEADERS = {"baggage": "splunk.trace.snapshot.volume=off"}


if __name__ == "__main__":
    from flask import Flask
    from opentelemetry import trace
    from werkzeug.serving import make_server

    app = Flask(__name__)
    shutdown_requested = Event()

    @app.route("/health")
    def health():
        return {"ready": True}

    @app.route("/work/<scenario>")
    def work(scenario):
        span_context = trace.get_current_span().get_span_context()
        # Keep the request active across multiple sampling intervals.
        time.sleep(0.25)
        return {
            "scenario": scenario,
            "trace_id": f"{span_context.trace_id:032x}",
            "span_id": f"{span_context.span_id:016x}",
        }

    @app.route("/stop")
    def stop():
        shutdown_requested.set()
        return {"stopped": True}

    with make_server(HOST, PORT, app) as server:
        server.timeout = 1
        deadline = time.monotonic() + 30
        while not shutdown_requested.is_set() and time.monotonic() < deadline:
            server.handle_request()
    assert shutdown_requested.is_set(), "HTTP test did not finish its requests"


def _get_json(path, headers):
    connection = http.client.HTTPConnection(HOST, PORT, timeout=5)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        assert response.status == 200
        return json.loads(response.read())
    finally:
        connection.close()


class DeclarativeFlaskCallgraphsOtelTest:
    def requirements(self):
        return (project_path(), "flask", "opentelemetry-instrumentation-flask")

    def declarative_configuration(self):
        return """
file_format: "1.0"
resource:
  attributes:
    - name: service.name
      value: yaml-flask-callgraphs
tracer_provider:
  processors:
    - simple:
        exporter:
          otlp_http:
            endpoint: http://localhost:4318/v1/traces
propagator:
  composite:
    - tracecontext: {}
    - baggage: {}
distribution:
  splunk:
    profiling:
      callgraphs:
        sampling_interval: 10
        selection_probability: 0.5
"""

    def environment_variables(self):
        return {
            "OTEL_TRACES_SAMPLER": "always_off",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "9999",
            "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": "1",
            "SPLUNK_PROFILER_LOGS_ENDPOINT": "http://localhost:1/unused",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:1/unused",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return True

    def on_start(self):
        wait_for_server(HOST, PORT, path="/health", headers=OFF_HEADERS)
        self.request_spans = []
        try:
            # Local probability uses the low 64 bits of these trace IDs.
            for scenario, trace_id, decision, selected in [
                ("local-selected", "1234567890abcdef0000000000000001", None, True),
                ("local-skipped", "2234567890abcdefffffffffffffffff", None, False),
                ("upstream-selected", "3234567890abcdefffffffffffffffff", "highest", True),
                ("upstream-disabled", "4234567890abcdef0000000000000002", "off", False),
            ]:
                headers = {"traceparent": f"00-{trace_id}-{PARENT_SPAN_ID}-01"}
                if decision is not None:
                    headers["baggage"] = f"splunk.trace.snapshot.volume={decision}"
                result = _get_json(f"/work/{scenario}", headers)
                assert result["scenario"] == scenario
                assert result["trace_id"] == trace_id
                assert result["span_id"] != "0" * 16
                self.request_spans.append((trace_id, result["span_id"], selected))
        finally:
            _get_json("/stop", OFF_HEADERS)

    def on_stop(self, telemetry, stdout, stderr, returncode):
        from lib import assert_snapshot_profile
        from opentelemetry.proto.trace.v1.trace_pb2 import Span
        from oteltest.telemetry import extract_leaves, get_attribute

        assert returncode == 0, stderr
        spans = extract_leaves(telemetry, "trace_requests", "pbreq", "resource_spans", "scope_spans", "spans")
        spans_by_id = {span.span_id.hex(): span for span in spans}
        selected_span_contexts = set()
        for trace_id, span_id, selected in self.request_spans:
            span = spans_by_id[span_id]
            assert span.kind == Span.SPAN_KIND_SERVER
            assert span.trace_id.hex() == trace_id
            assert span.parent_span_id.hex() == PARENT_SPAN_ID
            assert get_attribute(span.attributes, "http.route").value.string_value == "/work/<scenario>"
            selected_attribute = get_attribute(span.attributes, "splunk.snapshot.profiling")
            assert bool(selected_attribute and selected_attribute.value.bool_value) is selected
            if selected:
                selected_span_contexts.add((trace_id, span_id))
        assert_snapshot_profile(telemetry, sampling_interval=10, selected_span_contexts=selected_span_contexts)
