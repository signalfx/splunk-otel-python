# Copyright Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest

from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import INVALID_SPAN_CONTEXT, NonRecordingSpan, SpanContext, SpanKind, TraceFlags, use_span

from splunk_otel.mysql import execute_with_trace_context


class _FakeConnection:
    def __init__(self, *, failure_phase=None, failure_operation=None):
        self.traceparent = "previous-context"
        self.failure_phase = failure_phase
        self.failure_operation = failure_operation
        self.cursors = []

    def cursor(self):
        phase = "setup" if not self.cursors else "cleanup"
        cursor = _FakeInternalCursor(self, phase)
        self.cursors.append(cursor)
        self.fail_if_requested(phase, "cursor")
        return cursor

    def fail_if_requested(self, phase, operation):
        if (phase, operation) == (self.failure_phase, self.failure_operation):
            message = "internal failure"
            raise RuntimeError(message)


class _FakeInternalCursor:
    def __init__(self, connection, phase):
        self.connection = connection
        self.phase = phase
        self.closed = False

    def execute(self, statement, parameters):
        assert not is_instrumentation_enabled()
        assert statement == "SET @traceparent = %s"
        self.connection.traceparent = parameters[0]
        self.connection.fail_if_requested(self.phase, "execute")

    def close(self):
        assert not is_instrumentation_enabled()
        self.closed = True
        self.connection.fail_if_requested(self.phase, "close")


class _FakeQuery:
    def __init__(self, connection, *, error=None):
        self.connection = connection
        self.error = error
        self.result = object()
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs, self.connection.traceparent))
        assert is_instrumentation_enabled()
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.parametrize("flags", [TraceFlags.DEFAULT, TraceFlags.SAMPLED])
def test_execution_uses_supplied_context_and_clears_it(flags):
    connection = _FakeConnection()
    query = _FakeQuery(connection)
    database_context = SpanContext(0x123, 0x456, False, TraceFlags(flags))
    parent_context = SpanContext(0xABC, 0xDEF, False)

    with use_span(NonRecordingSpan(parent_context)):
        result = execute_with_trace_context(
            connection, query.execute, database_context, "SELECT %s", (17,), driver_option=True
        )

    assert result is query.result
    assert query.calls == [(("SELECT %s", (17,)), {"driver_option": True}, f"00-{0x123:032x}-{0x456:016x}-{flags:02x}")]
    assert connection.traceparent is None
    assert len(connection.cursors) == 2
    assert all(cursor.closed for cursor in connection.cursors)


def test_invalid_database_context_clears_previous_value_without_injecting_parent():
    connection = _FakeConnection()
    query = _FakeQuery(connection)
    parent_context = SpanContext(0xABC, 0xDEF, False, TraceFlags(TraceFlags.SAMPLED))

    with use_span(NonRecordingSpan(parent_context)):
        execute_with_trace_context(connection, query.execute, INVALID_SPAN_CONTEXT, "SELECT 1")

    assert query.calls == [(("SELECT 1",), {}, None)]
    assert connection.traceparent is None


@pytest.mark.parametrize("failure_phase", ["setup", "cleanup"])
@pytest.mark.parametrize("failure_operation", ["cursor", "execute", "close"])
@pytest.mark.parametrize("query_fails", [False, True])
def test_internal_failure_does_not_replace_query_result_or_error(failure_phase, failure_operation, query_fails, caplog):
    connection = _FakeConnection(failure_phase=failure_phase, failure_operation=failure_operation)
    query_error = ValueError("query failure") if query_fails else None
    query = _FakeQuery(connection, error=query_error)
    database_context = SpanContext(0x123, 0x456, False)

    if query_fails:
        with pytest.raises(ValueError, match="query failure") as caught:
            execute_with_trace_context(connection, query.execute, database_context, "SELECT 1")
        assert caught.value is query_error
    else:
        assert execute_with_trace_context(connection, query.execute, database_context, "SELECT 1") is query.result

    assert len(query.calls) == 1
    assert len(connection.cursors) == 2
    assert f"MySQL trace context {failure_phase} failed (RuntimeError)" in caplog.text
    if failure_phase == "setup":
        assert connection.traceparent is None


def test_query_error_clears_context_and_closes_internal_cursors():
    connection = _FakeConnection()
    error = ValueError("query failure")
    query = _FakeQuery(connection, error=error)

    with pytest.raises(ValueError, match="query failure") as caught:
        execute_with_trace_context(connection, query.execute, SpanContext(0x123, 0x456, False), "SELECT 1")

    assert caught.value is error
    assert connection.traceparent is None
    assert all(cursor.closed for cursor in connection.cursors)


def test_execution_uses_existing_database_span_without_creating_more_spans():
    connection = _FakeConnection()
    query = _FakeQuery(connection)
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        tracer = provider.get_tracer(__name__)
        with tracer.start_as_current_span("query", kind=SpanKind.CLIENT) as span:
            execute_with_trace_context(connection, query.execute, span.get_span_context(), "SELECT 1")
            context = span.get_span_context()
            assert query.calls[0][2] == (
                f"00-{context.trace_id:032x}-{context.span_id:016x}-{int(context.trace_flags):02x}"
            )
        assert len(exporter.get_finished_spans()) == 1
    finally:
        provider.shutdown()
