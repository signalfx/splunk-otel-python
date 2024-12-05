from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(12)


class ProfileOtelTest:
    def environment_variables(self):
        return {
            "SPLUNK_PROFILER_ENABLED": "true",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "500",  # not necessary, defaults to "1000" (ms)
            "SPLUNK_PROFILER_LOGS_ENDPOINT": "http://localhost:4317",  # not necessary, this is the default
        }

    def requirements(self):
        return (project_path(),)

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int):
        from oteltest.telemetry import count_logs, has_log_attribute

        assert count_logs(tel)
        assert has_log_attribute(tel, "profiling.data.format")

    def is_http(self):
        return False
