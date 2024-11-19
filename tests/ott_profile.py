from oteltest import Telemetry
from oteltest.telemetry import count_logs, has_log_attribute
from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(12)


class ProfileOtelTest:
    def environment_variables(self):
        return {
            "SPLUNK_PROFILER_ENABLED": "true",
        }

    def requirements(self):
        return [project_path(), "oteltest"]

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        pass

    def on_stop(self, tel: Telemetry, stdout: str, stderr: str, returncode: int):
        assert count_logs(tel)
        assert has_log_attribute(tel, "profiling.data.format")

    def is_http(self):
        return False
