import json

from lib import callgraph_trace_loop, project_path


if __name__ == "__main__":
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    callgraph_trace_loop()
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {"local-decision", "upstream-selected", "upstream-disabled"}
    selected_names = {"local-decision", "upstream-selected"}
    for span in spans:
        assert span.attributes.get("splunk.snapshot.profiling", False) == (span.name in selected_names)
    selected_span_ids = [f"{span.context.span_id:016x}" for span in spans if span.name in selected_names]
    print(json.dumps(selected_span_ids))  # noqa: T201


class DeclarativeCallgraphsOtelTest:
    def requirements(self):
        return (project_path(),)

    def declarative_configuration(self):
        return """
file_format: "1.0"
resource:
  attributes:
    - name: service.name
      value: yaml-callgraphs
propagator:
  composite:
    - tracecontext: {}
    - baggage: {}
distribution:
  splunk:
    profiling:
      callgraphs:
        selection_probability: 1
"""

    def environment_variables(self):
        return {
            "OTEL_TRACES_SAMPLER": "always_off",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "9999",
            "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": "0",
            "SPLUNK_PROFILER_LOGS_ENDPOINT": "http://localhost:1/unused",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:1/unused",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return True

    def on_start(self):
        pass

    def on_stop(self, telemetry, stdout, stderr, returncode):
        from lib import assert_snapshot_profile
        from oteltest.telemetry import extract_leaves, get_attribute

        assert returncode == 0, stderr
        selected_span_ids = set(json.loads(stdout))
        assert len(selected_span_ids) == 2
        assert_snapshot_profile(telemetry, sampling_interval=10, selected_span_ids=selected_span_ids)
        resources = extract_leaves(telemetry, "log_requests", "pbreq", "resource_logs", "resource")
        assert resources
        for resource in resources:
            assert get_attribute(resource.attributes, "service.name").value.string_value == "yaml-callgraphs"
