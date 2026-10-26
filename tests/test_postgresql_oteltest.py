import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opentelemetry.proto.trace.v1.trace_pb2 import Span


_SCRIPT_PATH = Path(__file__).parent / "integration" / "postgresql" / "trace_context.py"
_SPEC = importlib.util.spec_from_file_location("postgresql_trace_context", _SCRIPT_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


@pytest.fixture(autouse=True)
def instrumentation_mode(monkeypatch):
    monkeypatch.setenv("POSTGRESQL_TEST_INSTRUMENTATION", "auto")


def _fake_received_telemetry(spans):
    scope = SimpleNamespace(spans=spans)
    resource = SimpleNamespace(scope_spans=[scope])
    request = SimpleNamespace(pbreq=SimpleNamespace(resource_spans=[resource]))
    return SimpleNamespace(trace_requests=[request])


def _fake_query_results(*, propagation_enabled=True):
    spans = []
    results = []
    for index, driver in enumerate(("psycopg", "psycopg2", "psycopg-async"), 1):
        span = Span(
            trace_id=index.to_bytes(16, "big"),
            span_id=(index + 10).to_bytes(8, "big"),
            parent_span_id=(index + 20).to_bytes(8, "big"),
            kind=Span.SPAN_KIND_CLIENT,
            flags=0x100,
        )
        results.append(
            {
                "driver": driver,
                "parent_trace_id": span.trace_id.hex(),
                "parent_span_id": span.parent_span_id.hex(),
                "application_name": (
                    f"00-{span.trace_id.hex()}-{span.span_id.hex()}-03" if propagation_enabled else "startup-app"
                ),
            }
        )
        spans.append(span)
    return spans, results


def _fake_application_stdout(results):
    return "\n".join("POSTGRESQL_QUERY_RESULT " + json.dumps(result) for result in results)


@pytest.mark.parametrize("mode", ["auto", "manual", "disabled"])
def test_postgresql_oteltest_configures_startup_and_accepts_received_spans(monkeypatch, mode):
    monkeypatch.setenv("POSTGRESQL_TEST_INSTRUMENTATION", mode)
    monkeypatch.setenv("PGPORT", "55439")
    test = _MODULE.PostgreSQLTraceContextOtelTest()
    spans, results = _fake_query_results(propagation_enabled=mode != "disabled")

    test.on_stop(_fake_received_telemetry(spans), _fake_application_stdout(results), "", 0)

    environment = test.environment_variables()
    assert environment["SPLUNK_DB_TRACE_CONTEXT_PROPAGATION_ENABLED"] == str(mode != "disabled").lower()
    assert environment["POSTGRESQL_TEST_INSTRUMENTATION"] == mode
    assert environment["PGPORT"] == "55439"
    assert environment["OTEL_TRACES_EXPORTER"] == "otlp"
    assert test.wrapper_command() == ("" if mode == "manual" else "opentelemetry-instrument")
    assert test.requirements()[0] == str(Path(__file__).resolve().parent.parent)


def test_postgresql_oteltest_fails_for_application_errors():
    test = _MODULE.PostgreSQLTraceContextOtelTest()

    with pytest.raises(RuntimeError, match="exited with 1"):
        test.on_stop(_fake_received_telemetry([]), "", "query failed", 1)


def test_postgresql_oteltest_fails_for_missing_query_results():
    test = _MODULE.PostgreSQLTraceContextOtelTest()

    with pytest.raises(RuntimeError, match="Missing PostgreSQL query results"):
        test.on_stop(_fake_received_telemetry([]), "", "", 0)


@pytest.mark.parametrize("invalid_span", ["missing", "duplicate", "kind", "parent", "trace", "span", "flags"])
def test_postgresql_oteltest_fails_for_missing_or_mismatched_received_spans(invalid_span):
    test = _MODULE.PostgreSQLTraceContextOtelTest()
    spans, results = _fake_query_results()
    if invalid_span == "missing":
        spans.pop()
    elif invalid_span == "duplicate":
        spans.append(spans[0])
    elif invalid_span == "kind":
        spans[0].kind = Span.SPAN_KIND_SERVER
    elif invalid_span == "parent":
        spans[0].parent_span_id = b"mismatch"
    elif invalid_span == "trace":
        spans[0].trace_id = b"mismatch"
    elif invalid_span == "span":
        spans[0].span_id = b"mismatch"
    else:
        results[0]["application_name"] = results[0]["application_name"][:-2] + "zz"

    with pytest.raises(RuntimeError, match=r"CLIENT span|did not match"):
        test.on_stop(_fake_received_telemetry(spans), _fake_application_stdout(results), "", 0)


def test_postgresql_oteltest_rejects_trace_context_when_disabled(monkeypatch):
    monkeypatch.setenv("POSTGRESQL_TEST_INSTRUMENTATION", "disabled")
    test = _MODULE.PostgreSQLTraceContextOtelTest()
    spans, results = _fake_query_results()

    with pytest.raises(RuntimeError, match="did not match"):
        test.on_stop(_fake_received_telemetry(spans), _fake_application_stdout(results), "", 0)
