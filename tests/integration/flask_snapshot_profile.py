from __future__ import annotations

import http.client
import time

PORT = 8788
HOST = "127.0.0.1"


if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)

    @app.route("/work")
    def work():
        # Some CPU work so the profiler has something to sample
        total = 0
        for i in range(200_000):
            total += i * i
        return {"total": total}

    app.run(host=HOST, port=PORT, threaded=True)


class FlaskSnapshotProfileOtelTest:
    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "flask-snapshot-profile-test",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
            # 1.0 so every request is selected for profiling — required for deterministic test
            "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": "1.0",
            "SPLUNK_PROFILER_LOGS_ENDPOINT": "http://localhost:4317",
        }

    def requirements(self):
        from lib import project_path

        return (
            project_path(),
            "flask",
            "opentelemetry-instrumentation-flask",
        )

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def is_http(self):
        return False

    def on_start(self):
        from lib import wait_for_server

        wait_for_server(HOST, PORT, path="/work")

        # Hit the endpoint repeatedly for several seconds so the profiler has
        # multiple chances to tick (default interval: 10ms) while a span is active.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            conn = http.client.HTTPConnection(HOST, PORT)
            conn.request("GET", "/work")
            conn.getresponse()
            conn.close()
            time.sleep(0.1)

        # run the Flask subprocess for 10 more seconds
        return 10

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int):
        from lib import assert_snapshot_profile

        assert_snapshot_profile(tel)
