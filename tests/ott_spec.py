from oteltest.telemetry import extract_leaves, get_attribute, get_metric_names

from ott_lib import project_path, trace_loop

if __name__ == "__main__":
    trace_loop(1)


class SpecOtelTest:
    def requirements(self):
        return project_path(), "oteltest"

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-svc",
            "OTEL_METRICS_ENABLED": "true",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        assert_traces_to_spec(telemetry)
        assert_metrics_to_spec(telemetry)

    def is_http(self):
        return False


def assert_traces_to_spec(telemetry):
    attrs = extract_leaves(
        telemetry,
        "trace_requests",
        "pbreq",
        "resource_spans",
        "resource",
        "attributes"
    )
    assert get_attribute(attrs, "telemetry.sdk.name")
    assert get_attribute(attrs, "telemetry.sdk.version")
    assert get_attribute(attrs, "telemetry.sdk.language")
    assert get_attribute_str(attrs, "telemetry.distro.version")
    assert get_attribute_str(attrs, "telemetry.distro.name") == "splunk-opentelemetry"
    assert get_attribute(attrs, "process.pid")


def assert_metrics_to_spec(telemetry):
    # spot check system metrics instrumentor
    assert "system.cpu.time" in get_metric_names(telemetry)


def get_attribute_str(attributes, key):
    return get_attribute(attributes, key).value.string_value
