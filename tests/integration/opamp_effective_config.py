import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lib import project_path

_CONTENT_TYPE = "text/plain; format=properties; vendor=splunk; v=1.0.0"
_SERVICE_NAME = "opamp-effective-config-test"


def _assert_effective_config(request_path: Path) -> None:
    from opentelemetry._opamp.proto import opamp_pb2

    deadline = time.monotonic() + 10
    while not request_path.exists():
        assert time.monotonic() < deadline, "No OpAMP request received"
        time.sleep(0.05)

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(request_path.read_bytes())

    reports_effective_config = (
        opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsEffectiveConfig
    )
    assert message.capabilities & reports_effective_config
    assert message.HasField("effective_config")

    identifying_attributes = {
        attribute.key: attribute.value.string_value
        for attribute in message.agent_description.identifying_attributes
    }
    assert identifying_attributes["service.name"] == _SERVICE_NAME

    config_file = message.effective_config.config_map.config_map["environment"]
    assert config_file.content_type == _CONTENT_TYPE

    config = dict(
        line.split("=", maxsplit=1)
        for line in config_file.body.decode("utf-8").splitlines()
    )
    assert config == {
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://127.0.0.1:4318/v1/traces",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://127.0.0.1:4318/v1/metrics",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://127.0.0.1:4318/v1/logs",
        "SPLUNK_PROFILER_ENABLED": "false",
        "SPLUNK_PROFILER_MEMORY_ENABLED": "false",
        "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
        "SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL": "17",
        "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "1234",
        "OTEL_CONFIG_FILE": "null",
        "OTEL_EXPERIMENTAL_CONFIG_FILE": "null",
    }


if __name__ == "__main__":
    _assert_effective_config(Path(os.environ["OPAMP_TEST_REQUEST_FILE"]))


class _OpAMPRequestHandler(BaseHTTPRequestHandler):
    request_path: Path

    def do_POST(self) -> None:
        if (
            self.path != "/v1/opamp"
            or self.headers.get_content_type() != "application/x-protobuf"
        ):
            self.send_error(400)
            return

        content_length = int(self.headers["Content-Length"])
        body = self.rfile.read(content_length)
        if not self.request_path.exists():
            pending_path = self.request_path.with_suffix(".pending")
            pending_path.write_bytes(body)
            pending_path.replace(self.request_path)

        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, _format: str, *args) -> None:
        pass


class OpAMPEffectiveConfigOtelTest:
    def __init__(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._request_path = Path(self._temp_dir.name) / "request.pb"
        _OpAMPRequestHandler.request_path = self._request_path
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _OpAMPRequestHandler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="OpAMPTestServer",
            daemon=True,
        )
        self._server_thread.start()

    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        port = self._server.server_address[1]
        return {
            "NO_PROXY": "127.0.0.1,localhost",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
            "OTEL_SERVICE_NAME": _SERVICE_NAME,
            "OPAMP_TEST_REQUEST_FILE": str(self._request_path),
            "SPLUNK_OPAMP_ENABLED": "true",
            "SPLUNK_OPAMP_ENDPOINT": f"http://127.0.0.1:{port}/v1/opamp",
            "SPLUNK_OPAMP_POLLING_INTERVAL": "60000",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "1234",
            "SPLUNK_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "17",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_stop(self, _telemetry, stdout: str, stderr: str, returncode: int):
        try:
            assert returncode == 0, f"{stdout}\n{stderr}"
        finally:
            self._server.shutdown()
            self._server.server_close()
            self._server_thread.join(timeout=5)
            self._temp_dir.cleanup()

    def is_http(self):
        return True
