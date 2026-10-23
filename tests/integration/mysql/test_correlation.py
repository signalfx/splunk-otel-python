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

import os

import pytest

from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.trace import NoOpTracerProvider, SpanKind

from splunk_otel.mysql import enable_mysql_trace_context_propagation

mysql = pytest.importorskip("mysql.connector")
instrumentation = pytest.importorskip("opentelemetry.instrumentation.mysql")

pytestmark = pytest.mark.manual


@pytest.fixture
def span_exporter():
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    yield provider
    provider.shutdown()


@pytest.fixture(params=[True, False], ids=["python", "cext"])
def raw_connection(request):
    port = os.environ.get("MYSQL_CORRELATION_TEST_PORT")
    if not port:
        pytest.skip("Set MYSQL_CORRELATION_TEST_PORT to run against a disposable MySQL server")
    if not request.param and not mysql.HAVE_CEXT:
        pytest.skip("Connector/Python C extension is not installed")
    connection = mysql.connect(
        host="127.0.0.1",
        port=int(port),
        user="root",
        password="prototype-only",
        database="correlation",
        use_pure=request.param,
    )
    yield connection
    connection.close()


@pytest.fixture
def connection(raw_connection, tracer_provider):
    assert enable_mysql_trace_context_propagation()
    assert enable_mysql_trace_context_propagation()
    return instrumentation.MySQLInstrumentor().instrument_connection(raw_connection, tracer_provider=tracer_provider)


def _read_traceparent(raw_connection):
    with raw_connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT @traceparent")
        return cursor.fetchone()[0]


def _set_previous_context(raw_connection):
    with raw_connection.cursor() as cursor:
        cursor.execute("SET @traceparent = 'previous-context'")


@pytest.mark.parametrize("cursor_options", [{}, {"dictionary": True}, {"raw": True}])
def test_buffered_query_uses_database_child_span_and_keeps_rows(
    connection, raw_connection, tracer_provider, span_exporter, cursor_options
):
    with (
        tracer_provider.get_tracer(__name__).start_as_current_span("parent") as parent,
        connection.cursor(buffered=True, **cursor_options) as cursor,
    ):
        cursor.execute("SELECT @traceparent AS context, %s AS value;", (17,))
        assert _read_traceparent(raw_connection) is None
        row = cursor.fetchone()
    spans = span_exporter.get_finished_spans()
    database_span = next(span for span in spans if span.kind == SpanKind.CLIENT)
    context = database_span.context
    expected = f"00-{context.trace_id:032x}-{context.span_id:016x}-{int(context.trace_flags):02x}"
    if cursor_options.get("dictionary"):
        assert row == {"context": expected, "value": 17}
    elif cursor_options.get("raw"):
        assert row == (expected.encode(), b"17")
    else:
        assert row == (expected, 17)
    assert database_span.parent == parent.get_span_context()
    assert len(spans) == 2


@pytest.mark.parametrize(
    "operation",
    [
        "SELECT @traceparent; SELECT 2",
        "SELECT @traceparent /* comment */",
        "SELECT @traceparent -- comment\n",
        "SELECT @traceparent # comment\n",
        "SELECT /*! @traceparent */",
        "SELECT @traceparent, ';'",
        b"SELECT @traceparent",
    ],
)
def test_unsupported_sql_runs_without_session_commands(connection, raw_connection, operation):
    _set_previous_context(raw_connection)
    with connection.cursor(buffered=True) as cursor:
        cursor.execute(operation)
        assert cursor.fetchone()[0] == "previous-context"
        while cursor.nextset():
            if cursor.with_rows:
                cursor.fetchall()
    assert _read_traceparent(raw_connection) == "previous-context"


def test_unbuffered_query_keeps_unread_rows_and_session_value(connection, raw_connection):
    _set_previous_context(raw_connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT @traceparent UNION ALL SELECT 'second'")
        assert cursor.fetchall() == [("previous-context",), ("second",)]
    assert _read_traceparent(raw_connection) == "previous-context"


def test_prepared_cursor_runs_without_session_commands(connection, raw_connection):
    _set_previous_context(raw_connection)
    with connection.cursor(prepared=True) as cursor:
        cursor.execute("SELECT @traceparent")
        assert cursor.fetchall() == [("previous-context",)]
    assert _read_traceparent(raw_connection) == "previous-context"


def test_batch_runs_without_session_commands(connection, raw_connection, span_exporter):
    _set_previous_context(raw_connection)
    with raw_connection.cursor() as cursor:
        cursor.execute("CREATE TEMPORARY TABLE correlation_batch (context TEXT, value INT)")
    with connection.cursor(buffered=True) as cursor:
        cursor.executemany("INSERT INTO correlation_batch VALUES (@traceparent, %s)", [(17,), (23,)])
    with raw_connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT context, value FROM correlation_batch ORDER BY value")
        assert cursor.fetchall() == [("previous-context", 17), ("previous-context", 23)]
    assert _read_traceparent(raw_connection) == "previous-context"
    assert len(span_exporter.get_finished_spans()) == 1


def test_sqlcommenter_query_runs_without_session_commands(connection, raw_connection, tracer_provider, span_exporter):
    connection = instrumentation.MySQLInstrumentor().instrument_connection(
        raw_connection, tracer_provider=tracer_provider, enable_commenter=True
    )
    _set_previous_context(raw_connection)
    with connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT @traceparent")
        assert cursor.fetchone() == ("previous-context",)
    assert _read_traceparent(raw_connection) == "previous-context"
    assert len(span_exporter.get_finished_spans()) == 1


def test_pending_rows_are_left_to_the_driver(connection, raw_connection):
    _set_previous_context(raw_connection)
    with raw_connection.cursor() as pending, connection.cursor(buffered=True) as cursor:
        pending.execute("SELECT 17")
        with pytest.raises(mysql.InternalError):
            cursor.execute("SELECT @traceparent")
        assert pending.fetchall() == [(17,)]
    assert _read_traceparent(raw_connection) == "previous-context"


def test_stored_procedure_results_are_not_consumed(connection, raw_connection):
    _set_previous_context(raw_connection)
    with raw_connection.cursor() as cursor:
        cursor.execute("DROP PROCEDURE IF EXISTS correlation_results")
        cursor.execute("CREATE PROCEDURE correlation_results() BEGIN SELECT @traceparent; SELECT 2; END")
    try:
        with connection.cursor(buffered=True) as cursor:
            cursor.execute("CALL correlation_results()")
            assert cursor.fetchone() == ("previous-context",)
            assert cursor.nextset()
            assert cursor.fetchone() == (2,)
            while cursor.nextset():
                if cursor.with_rows:
                    cursor.fetchall()
        assert _read_traceparent(raw_connection) == "previous-context"
    finally:
        with raw_connection.cursor() as cursor:
            cursor.execute("DROP PROCEDURE correlation_results")


def test_suppressed_query_clears_context_without_injecting_parent(
    connection, raw_connection, tracer_provider, span_exporter
):
    _set_previous_context(raw_connection)
    with (
        tracer_provider.get_tracer(__name__).start_as_current_span("parent"),
        suppress_instrumentation(),
        connection.cursor(buffered=True) as cursor,
    ):
        cursor.execute("SELECT @traceparent")
        assert cursor.fetchone() == (None,)
    assert _read_traceparent(raw_connection) is None
    assert [span.name for span in span_exporter.get_finished_spans()] == ["parent"]


def test_noop_tracer_does_not_inject_parent(connection, raw_connection, tracer_provider):
    connection = instrumentation.MySQLInstrumentor().instrument_connection(
        raw_connection, tracer_provider=NoOpTracerProvider()
    )
    _set_previous_context(raw_connection)
    with (
        tracer_provider.get_tracer(__name__).start_as_current_span("parent"),
        connection.cursor(buffered=True) as cursor,
    ):
        cursor.execute("SELECT @traceparent")
        assert cursor.fetchone() == (None,)
    assert _read_traceparent(raw_connection) is None


def test_unsampled_database_context_is_propagated(connection, raw_connection):
    provider = TracerProvider(sampler=ALWAYS_OFF)
    connection = instrumentation.MySQLInstrumentor().instrument_connection(raw_connection, tracer_provider=provider)
    try:
        with provider.get_tracer(__name__).start_as_current_span("parent") as parent:
            with connection.cursor(buffered=True) as cursor:
                cursor.execute("SELECT @traceparent")
                value = cursor.fetchone()[0]
            context = parent.get_span_context()
            assert value.startswith(f"00-{context.trace_id:032x}-")
            assert value.split("-")[2] != f"{context.span_id:016x}"
            assert int(value.split("-")[3], 16) & 1 == 0
        assert _read_traceparent(raw_connection) is None
    finally:
        provider.shutdown()


def test_query_failure_clears_context_and_keeps_driver_error(connection, raw_connection, span_exporter):
    with connection.cursor(buffered=True) as cursor:
        with pytest.raises(mysql.ProgrammingError) as caught:
            cursor.execute("SELECT * FROM correlation_missing_table")
        assert caught.value.errno == 1146
        assert _read_traceparent(raw_connection) is None
        cursor.execute("SELECT @traceparent")
        assert cursor.fetchone()[0] is not None
    assert _read_traceparent(raw_connection) is None
    assert len(span_exporter.get_finished_spans()) == 2


@pytest.mark.parametrize("boundary", ["commit", "rollback"])
def test_transaction_boundary_has_no_completed_context(connection, raw_connection, span_exporter, boundary):
    with raw_connection.cursor() as cursor:
        cursor.execute(
            "CREATE TEMPORARY TABLE correlation_transaction (id INT AUTO_INCREMENT PRIMARY KEY, context TEXT)"
        )
    with connection.cursor(buffered=True) as cursor:
        cursor.execute("INSERT INTO correlation_transaction (context) VALUES (@traceparent)")
        assert cursor.rowcount == 1
        assert cursor.lastrowid == 1
    assert raw_connection.in_transaction
    assert _read_traceparent(raw_connection) is None
    getattr(connection, boundary)()
    assert _read_traceparent(raw_connection) is None
    with raw_connection.cursor(buffered=True) as cursor:
        cursor.execute("SELECT context FROM correlation_transaction")
        rows = cursor.fetchall()
    span = span_exporter.get_finished_spans()[0]
    context = span.context
    expected = f"00-{context.trace_id:032x}-{context.span_id:016x}-{int(context.trace_flags):02x}"
    assert rows == ([(expected,)] if boundary == "commit" else [])
    assert len(span_exporter.get_finished_spans()) == 1


def test_custom_cursor_is_not_correlated(connection, raw_connection):
    base = (
        mysql.cursor.MySQLCursorBuffered
        if isinstance(raw_connection, mysql.MySQLConnection)
        else mysql.cursor_cext.CMySQLCursorBuffered
    )

    class CustomCursor(base):
        pass

    _set_previous_context(raw_connection)
    with connection.cursor(cursor_class=CustomCursor) as cursor:
        cursor.execute("SELECT @traceparent")
        assert cursor.fetchone() == ("previous-context",)
    assert _read_traceparent(raw_connection) == "previous-context"


def test_automatic_instrumentation_uses_same_hook(raw_connection, tracer_provider, span_exporter):
    assert enable_mysql_trace_context_propagation()
    instrumentor = instrumentation.MySQLInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    try:
        with (
            mysql.connect(
                host="127.0.0.1",
                port=int(os.environ["MYSQL_CORRELATION_TEST_PORT"]),
                user="root",
                password="prototype-only",
                database="correlation",
                use_pure=isinstance(raw_connection, mysql.MySQLConnection),
            ) as connection,
            connection.cursor(buffered=True) as cursor,
        ):
            cursor.execute("SELECT @traceparent")
            value = cursor.fetchone()[0]
        context = span_exporter.get_finished_spans()[0].context
        assert value == f"00-{context.trace_id:032x}-{context.span_id:016x}-{int(context.trace_flags):02x}"
        assert len(span_exporter.get_finished_spans()) == 1
    finally:
        instrumentor.uninstrument()
