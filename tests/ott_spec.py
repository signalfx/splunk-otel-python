from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(1)


class SpecOtelTest:
    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-svc",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import extract_leaves, get_attribute

        attributes = extract_leaves(telemetry, "trace_requests", "pbreq", "resource_spans", "resource", "attributes")

        assert get_attribute(attributes, "telemetry.sdk.name")
        assert get_attribute(attributes, "telemetry.sdk.version")
        assert get_attribute(attributes, "telemetry.sdk.language")

    def is_http(self):
        return False
