from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(1)


class HttpProtocolOtelTest:
    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-otel-test",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        assert count_spans(telemetry)

    def is_http(self):
        return True
