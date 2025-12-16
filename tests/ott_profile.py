from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(12)


class ProfileOtelTest:
    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": __file__,
            "SPLUNK_PROFILER_ENABLED": "true",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "500",  # not necessary, defaults to "1000" (ms)
            "SPLUNK_PROFILER_LOGS_ENDPOINT": "http://localhost:4317",  # not necessary, this is the default
        }

    def requirements(self):
        return (project_path(),)

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return False

    def on_start(self):
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int):
        from oteltest.telemetry import extract_leaves, get_attribute

        scope_logs = extract_leaves(tel, "log_requests", "pbreq", "resource_logs", "scope_logs")
        profiling_scope_logs = [scope_log for scope_log in scope_logs if scope_log.scope.name == "otel.profiling"]
        fmt_attr = get_attribute(profiling_scope_logs[0].log_records[0].attributes, "profiling.data.format")
        assert fmt_attr.value.string_value == "pprof-gzip-base64"
