import time
from pathlib import Path

from opentelemetry import trace

UPSTREAM_PRERELEASE_VERSION = "0.62b0"


def project_path():
    return str(Path(__file__).parent.parent.parent)


def trace_loop(loops):
    tracer = trace.get_tracer("my-tracer")
    for _ in range(loops):
        with tracer.start_as_current_span("my-span"):
            time.sleep(0.5)


def wait_for_server(host, port, path="/", retries=20, delay=0.5):
    import http.client

    for _ in range(retries):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", path)
            conn.getresponse()
        except OSError:
            time.sleep(delay)
        else:
            conn.close()
            return
    msg = f"Server at {host}:{port} did not become ready"
    raise RuntimeError(msg)


def assert_snapshot_profile(tel):
    """
    Decode and validate snapshot profiling telemetry received by oteltest.

    Checks:
    - At least one otel.profiling scope log was received
    - profiling.data.format == pprof-gzip-base64
    - profiling.instrumentation.source == snapshot
    - pprof contains at least one sample
    - Every sample has a non-empty stack
    - Every sample has a valid (non-zero) trace_id and span_id
    """
    import base64
    import gzip
    import importlib.util

    # on_stop (which calls this function) runs in the oteltest venv, not the script's venv,
    # so splunk_otel is not installed. Load profile_pb2 directly by path -- a sys.path insert
    # would trigger splunk_otel/__init__.py which imports opentelemetry.sdk, also not installed.
    _pb2_path = Path(__file__).parent.parent.parent / "src" / "splunk_otel" / "profile_pb2.py"
    _spec = importlib.util.spec_from_file_location("profile_pb2", _pb2_path)
    profile_pb2 = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(profile_pb2)
    from oteltest.telemetry import extract_leaves, get_attribute

    scope_logs = extract_leaves(tel, "log_requests", "pbreq", "resource_logs", "scope_logs")
    profiling_scope_logs = [sl for sl in scope_logs if sl.scope.name == "otel.profiling"]
    assert profiling_scope_logs, "No otel.profiling scope logs received"

    log_record = profiling_scope_logs[0].log_records[0]

    fmt_attr = get_attribute(log_record.attributes, "profiling.data.format")
    assert fmt_attr.value.string_value == "pprof-gzip-base64"

    src_attr = get_attribute(log_record.attributes, "profiling.instrumentation.source")
    assert src_attr.value.string_value == "snapshot"

    encoded = log_record.body.string_value
    raw = gzip.decompress(base64.b64decode(encoded))
    profile = profile_pb2.Profile()
    profile.ParseFromString(raw)
    strings = list(profile.string_table)

    assert len(profile.sample) > 0, "pprof profile contains no samples"

    for sample in profile.sample:
        assert len(sample.location_id) > 0, "sample has empty stack"

        trace_id = ""
        span_id = ""
        for lbl in sample.label:
            key: str = str(strings[lbl.key])
            if key == "trace_id":
                trace_id = str(strings[lbl.str])
            elif key == "span_id":
                span_id = str(strings[lbl.str])

        assert trace_id, f"sample missing trace_id, got: {trace_id!r}"
        assert trace_id != "0" * 32, "sample has zero trace_id"
        assert span_id, f"sample missing span_id, got: {span_id!r}"
        assert span_id != "0" * 16, "sample has zero span_id"
