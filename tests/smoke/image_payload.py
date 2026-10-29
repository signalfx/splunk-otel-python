"""Run inside a stock Python container, using only the copied init-image payload."""

from concurrent.futures import ThreadPoolExecutor
import faulthandler
import importlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sitecustomize
import sqlite3
import subprocess
import sys
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from opentelemetry import _logs, metrics, trace
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import (
    add_LogsServiceServicer_to_server,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2_grpc import (
    add_MetricsServiceServicer_to_server,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import (
    add_TraceServiceServicer_to_server,
)
import grpc


def main():
    faulthandler.dump_traceback_later(30, exit=True)
    declarative = bool(os.environ.get("OTEL_CONFIG_FILE"))
    root = Path("/otel-auto-instrumentation-python")
    assert Path(sitecustomize.__file__) == root / "opentelemetry/instrumentation/auto_instrumentation/sitecustomize.py"
    assert not (root / "sitecustomize.py").exists()
    packages = root / f"python{sys.version_info.major}.{sys.version_info.minor}"
    for name in (
        "rpds.rpds",
        "grpc._cython.cygrpc",
        "wrapt._wrappers",
        "yaml._yaml",
        "charset_normalizer.cd",
        "charset_normalizer.md",
        "uuid_utils._uuid_utils",
        "google._upb._message",
        "psutil._psutil_linux",
    ):
        module = importlib.import_module(name)
        assert Path(module.__file__).is_relative_to(packages), module.__file__
    if os.environ.get("VERIFY_SECUREAPP") == "true":
        importlib.import_module("splunk_secureapp_opentelemetry_extension")
        assert importlib.metadata.version("secureapp-python-agent")

    received = {"traces": [], "metrics": [], "logs": []}
    request_types = {
        "traces": ExportTraceServiceRequest,
        "metrics": ExportMetricsServiceRequest,
        "logs": ExportLogsServiceRequest,
    }
    response_types = {
        "traces": ExportTraceServiceResponse,
        "metrics": ExportMetricsServiceResponse,
        "logs": ExportLogsServiceResponse,
    }

    class Receiver:
        def __init__(self, signal):
            self.signal = signal

        def Export(self, request, context):  # noqa: N802
            received[self.signal].append(request)
            return response_types[self.signal]()

    server = grpc.server(ThreadPoolExecutor(max_workers=3))
    add_TraceServiceServicer_to_server(Receiver("traces"), server)
    add_MetricsServiceServicer_to_server(Receiver("metrics"), server)
    add_LogsServiceServicer_to_server(Receiver("logs"), server)
    server.add_insecure_port("127.0.0.1:4317")
    server.start()

    class HTTPReceiver(BaseHTTPRequestHandler):
        def do_POST(self):
            signal = self.path.rsplit("/", 1)[-1]
            request = request_types[signal]()
            request.ParseFromString(self.rfile.read(int(self.headers["Content-Length"])))
            received[signal].append(request)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.end_headers()

        def log_message(self, *_args):
            pass

    http_server = HTTPServer(("127.0.0.1", 4318), HTTPReceiver)
    Thread(target=http_server.serve_forever, daemon=True).start()

    with trace.get_tracer("image-test").start_as_current_span("image-payload-span"):
        with sqlite3.connect(":memory:") as connection:
            connection.cursor().execute("SELECT 42").fetchall()
        metrics.get_meter("image-test").create_counter("image.payload.counter").add(1)
        logging.getLogger("image-test").warning("image-payload-log")

    for provider in (
        trace.get_tracer_provider(),
        metrics.get_meter_provider(),
        _logs.get_logger_provider(),
    ):
        assert provider.force_flush() is not False

    spans = [
        span
        for request in received["traces"]
        for resource in request.resource_spans
        for scope in resource.scope_spans
        for span in scope.spans
    ]
    assert any(span.name == "image-payload-span" for span in spans), received
    assert any("SELECT" in span.name for span in spans), spans
    assert any(
        metric.name == "image.payload.counter"
        for request in received["metrics"]
        for resource in request.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    ), received
    assert any(
        record.body.string_value == "image-payload-log"
        for request in received["logs"]
        for resource in request.resource_logs
        for scope in resource.scope_logs
        for record in scope.log_records
    ), received

    # A child must select its own dependencies and initialize from the same volume.
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from opentelemetry import trace; assert hasattr(trace.get_tracer_provider(), 'force_flush')",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert child.returncode == 0, child.stderr
    assert "Traceback" not in child.stderr, child.stderr
    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider(), _logs.get_logger_provider()):
        provider.shutdown()
    server.stop(0).wait()
    http_server.shutdown()
    http_server.server_close()
    faulthandler.cancel_dump_traceback_later()
    print(  # noqa: T201
        json.dumps(
            {
                "python": sys.version.split()[0],
                "declarative": declarative,
                "signals": list(received),
            }
        )
    )


if __name__ == "__main__":
    main()
