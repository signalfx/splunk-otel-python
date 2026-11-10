import importlib.util
from pathlib import Path

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from oteltest.telemetry import Request, Telemetry

from splunk_otel.profile import _pb_profile_to_str, _stacktraces_to_cpu_profile


@pytest.fixture(scope="module")
def profiling_integration_helpers():
    script_path = Path(__file__).parent / "integration" / "lib.py"
    spec = importlib.util.spec_from_file_location("profiling_integration_lib", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_received_profile(*, trace_id, span_id):
    profile = _stacktraces_to_cpu_profile(
        [{"frames": [("request.py", "work", 1)], "tid": 1}],
        {1: (trace_id, span_id)},
        interval_millis=10,
        time_seconds=1,
    )
    request = ExportLogsServiceRequest()
    scope_logs = request.resource_logs.add().scope_logs.add()
    scope_logs.scope.name = "otel.profiling"
    record = scope_logs.log_records.add()
    record.body.string_value = _pb_profile_to_str(profile)
    for key, value in [
        ("profiling.data.format", "pprof-gzip-base64"),
        ("profiling.instrumentation.source", "snapshot"),
    ]:
        attribute = record.attributes.add()
        attribute.key = key
        attribute.value.string_value = value
    return Telemetry(log_requests=[Request(request, {}, 0)])


@pytest.mark.parametrize("span_id", [1, 0x0123456789ABCDEF, 0x123456789ABCDEF0])
def test_profile_assertion_matches_span_ids_with_different_padding(profiling_integration_helpers, span_id):
    trace_id = 1
    telemetry = _fake_received_profile(trace_id=trace_id, span_id=span_id)

    profiling_integration_helpers.assert_snapshot_profile(
        telemetry,
        sampling_interval=10,
        selected_span_contexts={(f"{trace_id:032x}", f"{span_id:016x}")},
    )


def test_profile_assertion_rejects_a_different_span_id(profiling_integration_helpers):
    telemetry = _fake_received_profile(trace_id=1, span_id=1)

    with pytest.raises(AssertionError):
        profiling_integration_helpers.assert_snapshot_profile(
            telemetry, selected_span_contexts={(f"{1:032x}", f"{2:016x}")}
        )


@pytest.mark.parametrize(("trace_id", "span_id", "invalid_id"), [(0, 1, "trace_id"), (1, 0, "span_id")])
def test_profile_assertion_rejects_zero_ids(profiling_integration_helpers, trace_id, span_id, invalid_id):
    telemetry = _fake_received_profile(trace_id=trace_id, span_id=span_id)

    with pytest.raises(AssertionError, match=f"sample has zero {invalid_id}"):
        profiling_integration_helpers.assert_snapshot_profile(telemetry)
