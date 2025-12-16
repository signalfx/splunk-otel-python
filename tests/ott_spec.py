from ott_lib import project_path, trace_loop

SERVICE_NAME = "spec-svc"

if __name__ == "__main__":
    trace_loop(1)


class SpecOtelTest:
    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        return {
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
            "OTEL_SERVICE_NAME": SERVICE_NAME,
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import extract_leaves, get_attribute

        attributes = extract_leaves(
            telemetry,
            "trace_requests",
            "pbreq",
            "resource_spans",
            "resource",
            "attributes",
        )

        assert get_attribute(attributes, "telemetry.sdk.name")
        assert get_attribute(attributes, "telemetry.sdk.version")
        assert get_attribute(attributes, "telemetry.sdk.language")

        assert get_attribute(attributes, "telemetry.distro.version").value.string_value
        assert get_attribute(attributes, "telemetry.distro.name").value.string_value == "splunk-opentelemetry"

        assert get_attribute(attributes, "process.pid")

        assert get_attribute(attributes, "service.name").value.string_value == SERVICE_NAME

    def is_http(self):
        return False
