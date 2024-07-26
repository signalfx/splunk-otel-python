from tests.oteltest.lib import trace_loop

if __name__ == '__main__':
    trace_loop()


class MyOtelTest:

    def environment_variables(self):
        return {}

    def requirements(self):
        return (
            "dist/splunk_opentelemetry-2.0-py3-none-any.whl",
            "opentelemetry-exporter-otlp-proto-grpc==1.24.0",
        )

    def wrapper_command(self):
        return "splunk-py-trace"

    def on_start(self):
        print("on_start")

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        import oteltest.telemetry

        print("on_stop")
        assert len(oteltest.telemetry.stack_traces(tel)) == 16
