import base64
import gzip
import importlib.util
from pathlib import Path

from lib import project_path, trace_loop


if __name__ == "__main__":
    from opentelemetry import _logs

    trace_loop(3)
    _logs.get_logger_provider().force_flush()


class DeclarativeProfileOtelTest:
    def requirements(self):
        return (project_path(),)

    def declarative_configuration(self):
        config = Path(project_path(), "docs", "examples", "declarative-config.yaml").read_text()
        config = config.replace("${OTEL_SERVICE_NAME:-my-python-service}", "yaml-profile-service")
        return (
            config
            + """
distribution:
  splunk:
    profiling:
      always_on:
        cpu_profiler:
          sampling_interval: 250
"""
        )

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "environment-service",
            "SPLUNK_PROFILER_ENABLED": "false",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "9999",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return False

    def on_start(self):
        pass

    def on_stop(self, telemetry, stdout, stderr, returncode):
        from oteltest.telemetry import extract_leaves, get_attribute

        profile_path = Path(project_path(), "src", "splunk_otel", "profile_pb2.py")
        spec = importlib.util.spec_from_file_location("profile_pb2", profile_path)
        profile_pb2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile_pb2)

        assert returncode == 0, stderr
        resources = extract_leaves(telemetry, "log_requests", "pbreq", "resource_logs")
        profiles = []
        for resource_logs in resources:
            for scope_logs in resource_logs.scope_logs:
                if scope_logs.scope.name != "otel.profiling":
                    continue
                assert (
                    get_attribute(resource_logs.resource.attributes, "service.name").value.string_value
                    == "yaml-profile-service"
                )
                assert (
                    get_attribute(resource_logs.resource.attributes, "telemetry.distro.name").value.string_value
                    == "splunk-opentelemetry"
                )
                profiles.extend(scope_logs.log_records)

        assert profiles
        for record in profiles:
            assert (
                get_attribute(record.attributes, "profiling.instrumentation.source").value.string_value == "continuous"
            )
            profile = profile_pb2.Profile()
            profile.ParseFromString(gzip.decompress(base64.b64decode(record.body.string_value)))
            assert profile.sample
            for sample in profile.sample:
                (period,) = [
                    label.num for label in sample.label if profile.string_table[label.key] == "source.event.period"
                ]
                assert period == 250
