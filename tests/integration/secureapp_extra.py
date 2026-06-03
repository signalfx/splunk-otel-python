import base64
import gzip
import json
import os
import time

from lib import project_path, trace_loop

EVENT_NAME = "com.cisco.secureapp.report.v1"
SECUREAPP_SCOPE_NAME = "secureapp"
SERVICE_NAME = "secureapp-extra-test"


if __name__ == "__main__":
    import requests

    # SecureApp reports packages loaded in sys.modules; import a common
    # third-party package so the decoded dependency report has a stable target.
    assert requests.Session

    trace_loop(1)
    time.sleep(float(os.getenv("SECUREAPP_EXTRA_RUNTIME_SECONDS", "4")))


class SecureAppExtraOtelTest:
    def requirements(self):
        return (f"{project_path()}[secureapp]",)

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": SERVICE_NAME,
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
            "OTEL_BLRP_SCHEDULE_DELAY": "500",
            "SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY": "1",
            "SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL": "1",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        assert returncode == 0, f"script failed with stderr:\n{stderr}"
        assert count_spans(telemetry)

        records = _secureapp_dependency_records(telemetry)
        assert records, "No SecureApp dependency report logs received"

        reports = [_decode_dependency_report(record) for record in records]
        package_names = {package["name"].lower() for report in reports for package in report["packages"]}

        assert "secureapp-python-agent" in package_names
        assert "requests" in package_names

    def is_http(self):
        return True


def _secureapp_dependency_records(telemetry):
    from oteltest.telemetry import extract_leaves, get_attribute

    records = []
    scope_logs = extract_leaves(telemetry, "log_requests", "pbreq", "resource_logs", "scope_logs")
    for scope_log in scope_logs:
        if scope_log.scope.name != SECUREAPP_SCOPE_NAME:
            continue

        for record in scope_log.log_records:
            event_name = get_attribute(record.attributes, "event.name")
            if event_name and event_name.value.string_value == EVENT_NAME:
                records.append(record)

    return records


def _decode_dependency_report(record):
    encoded_body = record.body.string_value
    assert encoded_body

    raw = gzip.decompress(base64.b64decode(encoded_body))
    report = json.loads(raw.decode("utf-8"))

    assert report["id"]
    assert report["fragment_index"] >= 0
    assert report["max_fragments"] >= 1
    assert isinstance(report["is_done"], bool)
    assert isinstance(report["packages"], list)

    return report
