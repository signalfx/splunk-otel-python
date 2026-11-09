import logging
import time
from pathlib import Path

from lib import project_path, wait_for_server


if __name__ == "__main__":
    from opentelemetry import baggage, trace
    from opentelemetry._logs import LogRecord, get_logger

    get_logger("application").emit(LogRecord(body="application log"))
    selected_context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest")
    with trace.get_tracer("exporter-test").start_as_current_span("profiled-work", context=selected_context):
        time.sleep(0.5)


class DeclarativeCustomProfileExporterOtelTest:
    def requirements(self):
        return (project_path(),)

    def declarative_configuration(self):
        config_yaml = Path(project_path(), "docs", "examples", "declarative-config.yaml").read_text()
        return (
            config_yaml
            + """
distribution:
  splunk:
    profiling:
      exporter:
        otlp_log_http:
          endpoint: http://localhost:14318/v1/logs
          headers:
            - name: x-profile-test
              value: yaml-token
          timeout: 5000
      always_on:
        cpu_profiler:
          sampling_interval: 100
      callgraphs:
        sampling_interval: 25
"""
        )

    def environment_variables(self):
        return {
            "SPLUNK_PROFILER_LOGS_ENDPOINT": "http://localhost:1/unused",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:1/unused",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": "1",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return False

    def on_start(self):
        from oteltest.sink import HttpSink, raise_if_port_in_use
        from oteltest.sink.handler import AccumulatingHandler

        raise_if_port_in_use(14318)
        self.profile_handler = AccumulatingHandler()
        self.profile_sink = HttpSink(self.profile_handler, logging.getLogger(__name__), port=14318)
        self.profile_sink.start()
        wait_for_server("localhost", 14318)

    def on_stop(self, telemetry, stdout, stderr, returncode):
        from lib import assert_snapshot_profile
        from oteltest.telemetry import extract_leaves, get_attribute, get_logs

        self.profile_sink.stop()
        assert returncode == 0, stderr
        assert any(record.body.string_value == "application log" for record in get_logs(telemetry))
        application_scope_logs = extract_leaves(telemetry, "log_requests", "pbreq", "resource_logs", "scope_logs")
        assert all(scope.scope.name != "otel.profiling" for scope in application_scope_logs)

        profile_telemetry = self.profile_handler.telemetry
        profile_scope_logs = extract_leaves(profile_telemetry, "log_requests", "pbreq", "resource_logs", "scope_logs")
        assert profile_scope_logs
        assert all(scope.scope.name == "otel.profiling" and scope.log_records for scope in profile_scope_logs)
        sources = {
            get_attribute(record.attributes, "profiling.instrumentation.source").value.string_value
            for scope in profile_scope_logs
            for record in scope.log_records
        }
        assert sources == {"continuous", "snapshot"}
        assert_snapshot_profile(profile_telemetry, sampling_interval=25)
        for request in profile_telemetry.log_requests:
            headers = {key.lower(): value for key, value in request.headers.items()}
            assert headers["x-profile-test"] == "yaml-token"
