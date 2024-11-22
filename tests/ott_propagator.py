from typing import Mapping, Optional, Sequence

from oteltest import OtelTest, Telemetry
from ott_lib import project_path

PORT = 8888

HOST = "127.0.0.1"


def main():
    from flask import Flask

    app = Flask(__name__)

    @app.route("/")
    def home():
        return "hello"

    app.run(host=HOST, port=PORT)


if __name__ == "__main__":
    main()


class OTT(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {
            "OTEL_SERVICE_NAME": "my-svc",
        }

    def requirements(self) -> Sequence[str]:
        return [
            project_path(),
            "oteltest",
            "flask",
            "opentelemetry-instrumentation-flask",
        ]

    def wrapper_command(self) -> str:
        return "opentelemetry-instrument"

    def on_start(self) -> Optional[float]:
        import http.client
        import time

        time.sleep(6)

        conn = http.client.HTTPConnection(HOST, PORT)
        conn.request("GET", "/")

        response = conn.getresponse()
        assert_server_timing_headers_found(response)

        conn.close()

        return 6

    def on_stop(self, tel: Telemetry, stdout: str, stderr: str, returncode: int) -> None:
        pass

    def is_http(self) -> bool:
        pass


def assert_server_timing_headers_found(response):
    # Server-Timing: traceparent;desc="00-e899d68fca52b66d3facae0bdaf764db-159efb97d6b56568-01"
    # Access-Control-Expose-Headers: Server-Timing
    server_timing_header_found = False
    access_control_header_found = False
    for header, _ in response.getheaders():
        if header == "Server-Timing":
            server_timing_header_found = True
        elif header == "Access-Control-Expose-Headers":
            access_control_header_found = True
    assert server_timing_header_found
    assert access_control_header_found
