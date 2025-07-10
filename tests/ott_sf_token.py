from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(12)


class AccessTokenOtelTest:
    def requirements(self):
        return project_path(), "oteltest"

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-svc",
            "SPLUNK_ACCESS_TOKEN": "s3cr3t",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        for request in telemetry.get_trace_requests():
            assert request.headers.get("x-sf-token") == "s3cr3t"

    def is_http(self):
        return False
