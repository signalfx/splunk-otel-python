import time
from pathlib import Path

from opentelemetry import trace

UPSTREAM_PRERELEASE_VERSION = "0.66b1"


def project_path():
    return str(Path(__file__).parent.parent.parent)


def trace_loop(loops):
    tracer = trace.get_tracer("my-tracer")
    for _ in range(loops):
        with tracer.start_as_current_span("my-span"):
            time.sleep(0.5)


def wait_for_server(host, port, path="/", retries=20, delay=0.5, *, headers=None):
    import http.client

    for _ in range(retries):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", path, headers=headers or {})
            conn.getresponse()
        except OSError:
            time.sleep(delay)
        else:
            conn.close()
            return
    msg = f"Server at {host}:{port} did not become ready"
    raise RuntimeError(msg)


def assert_snapshot_profile(tel, *, sampling_interval=None, selected_span_contexts=None):
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

    snapshot_records = [
        record
        for scope in profiling_scope_logs
        for record in scope.log_records
        if get_attribute(record.attributes, "profiling.instrumentation.source").value.string_value == "snapshot"
    ]
    assert snapshot_records, "No snapshot profiles received"
    sampled_span_contexts = set()
    for log_record in snapshot_records:
        fmt_attr = get_attribute(log_record.attributes, "profiling.data.format")
        assert fmt_attr.value.string_value == "pprof-gzip-base64"

        raw = gzip.decompress(base64.b64decode(log_record.body.string_value))
        profile = profile_pb2.Profile()
        profile.ParseFromString(raw)
        strings = list(profile.string_table)
        assert profile.sample, "pprof profile contains no samples"
        for sample in profile.sample:
            assert sample.location_id, "sample has empty stack"
            labels = {strings[label.key]: strings[label.str] for label in sample.label}
            trace_id = labels.get("trace_id")
            span_id = labels.get("span_id")
            assert trace_id, "sample has no trace_id"
            assert span_id, "sample has no span_id"
            trace_id = f"{int(trace_id, 16):032x}"
            span_id = f"{int(span_id, 16):016x}"
            assert trace_id != "0" * 32, "sample has zero trace_id"
            assert span_id != "0" * 16, "sample has zero span_id"
            sampled_span_contexts.add((trace_id, span_id))
            if sampling_interval is not None:
                (period,) = [label.num for label in sample.label if strings[label.key] == "source.event.period"]
                assert period == sampling_interval
    if selected_span_contexts is not None:
        assert selected_span_contexts <= sampled_span_contexts, (
            f"Missing request profiles: {selected_span_contexts - sampled_span_contexts}"
        )
        # Framework entry/exit can also be sampled with the incoming remote parent current.
        sampled_trace_ids = {trace_id for trace_id, _span_id in sampled_span_contexts}
        selected_trace_ids = {trace_id for trace_id, _span_id in selected_span_contexts}
        assert sampled_trace_ids == selected_trace_ids, (
            f"Unexpected profiled traces: {sampled_trace_ids - selected_trace_ids}"
        )
