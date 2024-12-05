from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(1)


class SpecOtelTest:
    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        return {
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import extract_leaves, get_attribute

        assert "service.name attribute is not set" in stderr

        attributes = extract_leaves(
            telemetry,
            "trace_requests",
            "pbreq",
            "resource_spans",
            "resource",
            "attributes",
        )
        assert get_attribute(attributes, "service.name").value.string_value == "unnamed-python-service"

    def is_http(self):
        return False
