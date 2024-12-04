from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(1)


class SpecOtelTest:
    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        return {}

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import extract_leaves, get_attribute

        def get_attribute_str(attrs, key):
            return get_attribute(attrs, key).value.string_value

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

        assert get_attribute_str(attributes, "telemetry.distro.version")
        assert get_attribute_str(attributes, "telemetry.distro.name") == "splunk-opentelemetry"

        assert get_attribute(attributes, "process.pid")

    def is_http(self):
        return False
