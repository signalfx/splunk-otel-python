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

import asyncio
import inspect
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from splunk_otel.postgresql import (
    _AsyncDriverCursor,
    _CursorAdapter,
    _SyncDriverCursor,
    _cursor_factory_wrapper,
    _execute_with_postgresql_trace_context,
    _execute_with_postgresql_trace_context_async,
)
from splunk_otel import postgresql


PARENT_CONTEXT = SpanContext(
    trace_id=0x11111111111111111111111111111111,
    span_id=0x1111111111111111,
    is_remote=False,
    trace_flags=TraceFlags(TraceFlags.SAMPLED),
)
DATABASE_CONTEXT = SpanContext(
    trace_id=PARENT_CONTEXT.trace_id,
    span_id=0x2222222222222222,
    is_remote=False,
    trace_flags=TraceFlags(TraceFlags.SAMPLED),
)
SECOND_DATABASE_CONTEXT = SpanContext(
    trace_id=PARENT_CONTEXT.trace_id,
    span_id=0x3333333333333333,
    is_remote=False,
    trace_flags=TraceFlags(TraceFlags.SAMPLED),
)
INNER_DATABASE_CONTEXT = SpanContext(
    trace_id=PARENT_CONTEXT.trace_id,
    span_id=0x4444444444444444,
    is_remote=False,
    trace_flags=TraceFlags(TraceFlags.SAMPLED),
)
TRACEPARENT = "00-11111111111111111111111111111111-2222222222222222-01"
SECOND_TRACEPARENT = "00-11111111111111111111111111111111-3333333333333333-01"
INNER_TRACEPARENT = "00-11111111111111111111111111111111-4444444444444444-01"


class FakeConnection:
    def __init__(self):
        self.default_application_name = "startup-app"
        self.application_name = "customer-app"
        self.calls = []
        self.cursors = []
        self.info = SimpleNamespace(pipeline_status=0)
        self.before_execute = lambda _query: None

    def cursor(self):
        cursor = FakePsycopgCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.calls.append("COMMIT")
        return self.application_name


class FakeAsyncConnection(FakeConnection):
    def cursor(self):
        cursor = FakeAsyncPsycopgCursor(self)
        self.cursors.append(cursor)
        return cursor


class _FakeDriverCursor:
    __module__ = "psycopg"

    def __init__(self, connection):
        self.connection = connection
        self.calls = []
        self.closed = False

    def execute(self, query, parameters=None):
        call = (query, parameters) if parameters is not None else query
        self.calls.append(call)
        self.connection.calls.append(call)
        self.connection.before_execute(query)
        if query == "SET application_name = DEFAULT":
            self.connection.application_name = self.connection.default_application_name
        elif query == "SELECT pg_catalog.set_config('application_name', %s, false)":
            self.connection.application_name = parameters[0]
        return self.connection.application_name

    def close(self):
        self.closed = True

    def executemany(self, query, parameters_list):
        self.connection.info.pipeline_status = 1
        try:
            for parameters in parameters_list:
                _FakeDriverCursor.execute(self, query, parameters)
        finally:
            self.connection.info.pipeline_status = 0

    def callproc(self, name):
        return _FakeDriverCursor.execute(self, name)


class _FakeAsyncDriverCursor:
    __module__ = "psycopg.fake"

    def __init__(self, connection):
        self.connection = connection
        self.calls = []
        self.closed = False

    async def execute(self, query, parameters=None):
        call = (query, parameters) if parameters is not None else query
        self.calls.append(call)
        self.connection.calls.append(call)
        result = self.connection.before_execute(query)
        if inspect.isawaitable(result):
            await result
        if query == "SET application_name = DEFAULT":
            self.connection.application_name = self.connection.default_application_name
        elif query == "SELECT pg_catalog.set_config('application_name', %s, false)":
            self.connection.application_name = parameters[0]
        return self.connection.application_name

    async def close(self):
        self.closed = True

    async def executemany(self, query, parameters_list):
        self.connection.info.pipeline_status = 1
        try:
            for parameters in parameters_list:
                await _FakeAsyncDriverCursor.execute(self, query, parameters)
        finally:
            self.connection.info.pipeline_status = 0


def _fake_internal_cursor_factory(connection):
    return connection.cursor()


class FakePsycopgCursor(_SyncDriverCursor, _FakeDriverCursor):
    _new_internal_cursor = staticmethod(_fake_internal_cursor_factory)


class FakeAsyncPsycopgCursor(_AsyncDriverCursor, _FakeAsyncDriverCursor):
    _new_internal_cursor = staticmethod(_fake_internal_cursor_factory)


@pytest.fixture(autouse=True)
def fake_cursor_adapters(monkeypatch):
    def _fake_cursor_factory(db_api=None, base_factory=None):  # noqa: ARG001
        return base_factory

    module = SimpleNamespace(_new_cursor_factory=_fake_cursor_factory)
    adapter = _CursorAdapter(
        module=module,
        factory_name="_new_cursor_factory",
        base_cursor=_FakeDriverCursor,
        new_internal_cursor=_fake_internal_cursor_factory,
    )
    monkeypatch.setattr(postgresql, "_load_cursor_adapters", lambda: [adapter])
    return module


def _fake_traced_execution(_cursor, query_method, *args, **kwargs):
    with trace.use_span(NonRecordingSpan(DATABASE_CONTEXT)):
        return query_method(*args, **kwargs)


async def _fake_traced_execution_async(_cursor, query_method, *args, **kwargs):
    with trace.use_span(NonRecordingSpan(DATABASE_CONTEXT)):
        return await query_method(*args, **kwargs)


def _fake_nested_traced_execution(_cursor, query_method, *args, **kwargs):
    with trace.use_span(NonRecordingSpan(SECOND_DATABASE_CONTEXT)):
        return query_method(*args, **kwargs)


async def _fake_nested_traced_execution_async(_cursor, query_method, *args, **kwargs):
    with trace.use_span(NonRecordingSpan(SECOND_DATABASE_CONTEXT)):
        return await query_method(*args, **kwargs)


def _fake_inner_traced_execution(_cursor, query_method, *args, **kwargs):
    with trace.use_span(NonRecordingSpan(INNER_DATABASE_CONTEXT)):
        return query_method(*args, **kwargs)


def _fake_untraced_execution(_cursor, query_method, *args, **kwargs):
    return query_method(*args, **kwargs)


@pytest.mark.parametrize("pipeline_status", [1, 2])
@pytest.mark.parametrize("query_fails", [False, True])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_pipeline_queries_send_no_internal_commands(pipeline_status, query_fails, asynchronous, caplog):
    connection = FakeAsyncConnection() if asynchronous else FakeConnection()
    connection.info = SimpleNamespace(pipeline_status=pipeline_status)
    cursor = connection.cursor()
    error = RuntimeError("customer pipeline query failed")

    def _fake_customer_query_failure(_query):
        if query_fails:
            raise error

    connection.before_execute = _fake_customer_query_failure

    def run():
        if asynchronous:
            return asyncio.run(
                _execute_with_postgresql_trace_context_async(
                    _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT 1"), {}
                )
            )
        return _execute_with_postgresql_trace_context(
            _fake_traced_execution, None, (cursor, cursor.execute, "SELECT 1"), {}
        )

    if query_fails:
        with pytest.raises(RuntimeError) as raised:
            run()
        assert raised.value is error
    else:
        assert run() == "customer-app"
    assert connection.calls == ["SELECT 1"]
    assert connection.cursors == [cursor]
    assert not caplog.records


@pytest.mark.parametrize("nested_fails", [False, True])
def test_custom_cursor_queries_run_before_outer_driver_execution(nested_fails):
    connection = FakeConnection()
    error = RuntimeError("nested query failed")
    results = []

    def _fake_query_failure(query):
        if nested_fails and query == "SELECT nested":
            raise error

    connection.before_execute = _fake_query_failure

    class CustomerCursor(FakePsycopgCursor):
        def execute(self, query):
            nested = FakePsycopgCursor(connection)
            with pytest.raises(RuntimeError) if nested_fails else nullcontext() as raised:
                result = _execute_with_postgresql_trace_context(
                    _fake_nested_traced_execution, None, (nested, nested.execute, "SELECT nested"), {}
                )
                assert result == SECOND_TRACEPARENT
            if nested_fails:
                assert raised.value is error
            assert connection.application_name == "startup-app"
            return super().execute(query)

    cursor = CustomerCursor(connection)

    def _execute_customer_query():
        results.append(
            _execute_with_postgresql_trace_context(
                _fake_traced_execution, None, (cursor, cursor.execute, "SELECT outer"), {}
            )
        )

    thread = threading.Thread(target=_execute_customer_query, daemon=True)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive(), "Nested customer query deadlocked"
    assert results == [TRACEPARENT]
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (SECOND_TRACEPARENT,)),
        "SELECT nested",
        "SET application_name = DEFAULT",
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "SELECT outer",
        "SET application_name = DEFAULT",
    ]


@pytest.mark.parametrize("nested_fails", [False, True])
def test_async_custom_cursor_queries_run_before_outer_driver_execution(nested_fails):
    async def run():
        connection = FakeAsyncConnection()
        error = RuntimeError("nested query failed")

        def _fake_query_failure(query):
            if nested_fails and query == "SELECT nested":
                raise error

        connection.before_execute = _fake_query_failure

        class CustomerCursor(FakeAsyncPsycopgCursor):
            async def execute(self, query):
                nested = FakeAsyncPsycopgCursor(connection)
                with pytest.raises(RuntimeError) if nested_fails else nullcontext() as raised:
                    result = await _execute_with_postgresql_trace_context_async(
                        _fake_nested_traced_execution_async, None, (nested, nested.execute, "SELECT nested"), {}
                    )
                    assert result == SECOND_TRACEPARENT
                if nested_fails:
                    assert raised.value is error
                assert connection.application_name == "startup-app"
                return await super().execute(query)

        cursor = CustomerCursor(connection)
        result = await asyncio.wait_for(
            _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT outer"), {}
            ),
            timeout=2,
        )
        assert result == TRACEPARENT
        assert connection.calls == [
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (SECOND_TRACEPARENT,)),
            "SELECT nested",
            "SET application_name = DEFAULT",
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
            "SELECT outer",
            "SET application_name = DEFAULT",
        ]

    asyncio.run(run())


def test_async_custom_cursor_can_await_auxiliary_task_before_outer_query():
    async def run():
        connection = FakeAsyncConnection()
        nested_started = asyncio.Event()
        children = []

        async def _execute_nested_customer_query():
            nested_started.set()
            cursor = FakeAsyncPsycopgCursor(connection)
            return await _execute_with_postgresql_trace_context_async(
                _fake_nested_traced_execution_async, None, (cursor, cursor.execute, "SELECT child"), {}
            )

        class CustomerCursor(FakeAsyncPsycopgCursor):
            async def execute(self, query):
                children.append(asyncio.create_task(_execute_nested_customer_query()))
                await nested_started.wait()
                assert await children[0] == SECOND_TRACEPARENT
                assert connection.application_name == "startup-app"
                return await super().execute(query)

        cursor = CustomerCursor(connection)
        result = await _execute_with_postgresql_trace_context_async(
            _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT outer"), {}
        )
        assert result == TRACEPARENT
        assert connection.calls == [
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (SECOND_TRACEPARENT,)),
            "SELECT child",
            "SET application_name = DEFAULT",
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
            "SELECT outer",
            "SET application_name = DEFAULT",
        ]

    asyncio.run(asyncio.wait_for(run(), timeout=2))


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "statement",
    [
        "BEGIN",
        "START TRANSACTION",
        "COMMIT",
        "END;",
        "ROLLBACK",
        "ABORT",
        "SAVEPOINT customer_savepoint",
        "RELEASE SAVEPOINT customer_savepoint",
        "ROLLBACK TO SAVEPOINT customer_savepoint",
        "PREPARE TRANSACTION 'customer_transaction'",
        "COMMIT PREPARED 'customer_transaction'",
        "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        "SET TRANSACTION READ ONLY",
        "SET TRANSACTION DEFERRABLE",
        "SET TRANSACTION SNAPSHOT '00000003-0000001B-1'",
        "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        "SET transaction_isolation = 'serializable'",
        "SET SESSION transaction_isolation TO 'repeatable read'",
        "SET LOCAL \"transaction_isolation\" = 'serializable'",
        "SET transaction_read_only = on",
        "SET LOCAL transaction_deferrable = on",
        "-- customer comment\n SET /* outer /* nested */ comment */ TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        "set /* setting */ local /* name */ \"transaction_isolation\" to 'serializable';",
        b"SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        "CALL customer_procedure()",
        "DO $$ BEGIN COMMIT; END $$",
        "SELECT 1; COMMIT",
        "SELECT 1; BEGIN",
        "-- customer comment\n COMMIT",
        "/* outer /* nested */ comment */ BEGIN",
        b"COMMIT",
    ],
)
def test_transaction_control_and_batches_send_only_customer_statement(statement, asynchronous):
    if asynchronous:

        async def run():
            connection = FakeAsyncConnection()
            cursor = FakeAsyncPsycopgCursor(connection)
            result = await _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async, None, (cursor, cursor.execute, statement), {}
            )
            assert result == "customer-app"
            assert connection.calls == [statement]
            assert connection.cursors == []

        asyncio.run(run())
    else:
        connection = FakeConnection()
        cursor = FakePsycopgCursor(connection)
        result = _execute_with_postgresql_trace_context(
            _fake_traced_execution, None, (cursor, cursor.execute, statement), {}
        )
        assert result == "customer-app"
        assert connection.calls == [statement]
        assert connection.cursors == []


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT 1;",
        "-- comment\nSELECT 1",
        "/* outer /* nested */ comment */ SELECT 1",
        "SET statement_timeout = '1s'",
        "SET LOCAL statement_timeout = '1s'",
        "SET SESSION \"statement_timeout\" = '1s'",
        "SET \"myapp.transaction_isolation\" = 'serializable'",
    ],
)
def test_statement_without_transaction_configuration_propagates_context(statement):
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)
    assert (
        _execute_with_postgresql_trace_context(_fake_traced_execution, None, (cursor, cursor.execute, statement), {})
        == TRACEPARENT
    )


@pytest.mark.parametrize("statement", ["(SELECT 1)", "((SELECT 1)) UNION (SELECT 2)", "/* comment */ (SELECT 1)"])
def test_parenthesized_queries_propagate_context(statement):
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)
    result = _execute_with_postgresql_trace_context(
        _fake_traced_execution, None, (cursor, cursor.execute, statement), {}
    )
    assert result == TRACEPARENT
    assert connection.application_name == "startup-app"


def test_callproc_function_name_is_not_a_transaction_command():
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)
    result = _execute_with_postgresql_trace_context(
        _fake_traced_execution, None, (cursor, cursor.callproc, "begin_job"), {}
    )
    assert result == TRACEPARENT
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "begin_job",
        "SET application_name = DEFAULT",
    ]


def test_delayed_callback_acquires_lock_and_does_not_restore_finished_context(monkeypatch):
    async def run():
        connection = FakeConnection()
        acquisitions = []
        results = []
        loop = asyncio.get_running_loop()
        completed = loop.create_future()

        class ConnectionLock:
            def __enter__(self):
                acquisitions.append("acquired")

            def __exit__(self, *_args):
                pass

        monkeypatch.setattr(postgresql, "_get_sync_connection_lock", lambda _connection: ConnectionLock())

        def _execute_delayed_query():
            cursor = FakePsycopgCursor(connection)
            results.append(
                _execute_with_postgresql_trace_context(
                    _fake_nested_traced_execution, None, (cursor, cursor.execute, "SELECT delayed"), {}
                )
            )
            completed.set_result(None)

        def _fake_schedule_callback(query):
            if query == "SELECT outer":
                loop.call_soon(_execute_delayed_query)

        connection.before_execute = _fake_schedule_callback
        cursor = FakePsycopgCursor(connection)
        assert (
            _execute_with_postgresql_trace_context(
                _fake_traced_execution, None, (cursor, cursor.execute, "SELECT outer"), {}
            )
            == TRACEPARENT
        )
        await asyncio.wait_for(completed, timeout=1)
        assert results == [SECOND_TRACEPARENT]
        assert acquisitions == ["acquired", "acquired"]
        assert connection.application_name == "startup-app"
        assert connection.calls[-1] == "SET application_name = DEFAULT"

    asyncio.run(run())


def test_skipped_driver_query_keeps_inherited_outer_setting():
    connection = FakeConnection()

    def _fake_nested_driver_calls(query):
        if query == "SELECT outer":
            middle = FakePsycopgCursor(connection)
            result = _execute_with_postgresql_trace_context(
                _fake_nested_traced_execution, None, (middle, middle.execute, "SELECT ';'"), {}
            )
            assert result == TRACEPARENT
        elif query == "SELECT ';'":
            inner = FakePsycopgCursor(connection)
            result = _execute_with_postgresql_trace_context(
                _fake_inner_traced_execution, None, (inner, inner.execute, "SELECT inner"), {}
            )
            assert result == INNER_TRACEPARENT

    connection.before_execute = _fake_nested_driver_calls
    cursor = FakePsycopgCursor(connection)
    result = _execute_with_postgresql_trace_context(
        _fake_traced_execution, None, (cursor, cursor.execute, "SELECT outer"), {}
    )
    assert result == TRACEPARENT
    assert connection.application_name == "startup-app"


def test_query_sets_database_span_traceparent():
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    with trace.use_span(NonRecordingSpan(PARENT_CONTEXT)):
        result = _execute_with_postgresql_trace_context(
            _fake_traced_execution,
            None,
            (cursor, cursor.execute, "SELECT application_name"),
            {},
        )

    assert result == TRACEPARENT
    assert cursor.calls == ["SELECT application_name"]
    assert connection.cursors[0].calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,))
    ]
    assert all(internal_cursor.closed for internal_cursor in connection.cursors)
    assert connection.application_name == "startup-app"
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "SELECT application_name",
        "SET application_name = DEFAULT",
    ]


def test_query_without_database_span_clears_stale_traceparent():
    connection = FakeConnection()
    connection.application_name = TRACEPARENT
    cursor = FakePsycopgCursor(connection)
    result = _execute_with_postgresql_trace_context(
        _fake_untraced_execution,
        None,
        (cursor, cursor.execute, "SELECT 2"),
        {},
    )

    assert result == "startup-app"
    assert connection.calls == [
        "SET application_name = DEFAULT",
        "SELECT 2",
    ]


def test_non_postgresql_cursor_is_unchanged():
    class OtherCursor:
        pass

    cursor = OtherCursor()
    calls = []

    def wrapped(*args, **kwargs):
        calls.append((args, kwargs))
        return "result"

    assert _execute_with_postgresql_trace_context(wrapped, None, (cursor, "query", "SELECT 1"), {}) == "result"
    assert calls == [((cursor, "query", "SELECT 1"), {})]


def test_suppressed_instrumentation_is_unchanged():
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    with suppress_instrumentation():
        result = _execute_with_postgresql_trace_context(
            _fake_traced_execution,
            None,
            (cursor, cursor.execute, "SELECT 1"),
            {},
        )

    assert result == "customer-app"
    assert cursor.calls == ["SELECT 1"]
    assert connection.cursors == []


def test_psycopg2_asynchronous_connection_sends_only_customer_query():
    class FakePsycopg2Cursor(FakePsycopgCursor):
        __module__ = "psycopg2.extensions"

    connection = FakeConnection()
    connection.async_ = 1
    cursor = FakePsycopg2Cursor(connection)

    _execute_with_postgresql_trace_context(
        _fake_traced_execution,
        None,
        (cursor, cursor.execute, "SELECT 1"),
        {},
    )

    assert connection.calls == ["SELECT 1"]
    assert connection.cursors == []


def test_psycopg2_named_cursor_sends_only_customer_query():
    class FakePsycopg2NamedCursor(FakePsycopgCursor):
        __module__ = "psycopg2.extensions"

        def execute(self, query):
            if self.calls:
                raise RuntimeError
            return super().execute(query)

    connection = FakeConnection()
    cursor = FakePsycopg2NamedCursor(connection)
    cursor.name = "server_cursor"

    with trace.use_span(NonRecordingSpan(PARENT_CONTEXT)):
        result = _execute_with_postgresql_trace_context(
            _fake_traced_execution,
            None,
            (cursor, cursor.execute, "SELECT 1"),
            {},
        )

    assert result == "customer-app"
    assert cursor.calls == ["SELECT 1"]
    assert connection.cursors == []


def test_async_query_sets_database_span_traceparent():
    async def run():
        connection = FakeAsyncConnection()
        cursor = FakeAsyncPsycopgCursor(connection)

        with trace.use_span(NonRecordingSpan(PARENT_CONTEXT)):
            result = await _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async,
                None,
                (cursor, cursor.execute, "SELECT application_name"),
                {},
            )

        return result, connection, cursor

    result, connection, cursor = asyncio.run(run())

    assert result == TRACEPARENT
    assert cursor.calls == ["SELECT application_name"]
    assert connection.cursors[0].calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,))
    ]
    assert all(internal_cursor.closed for internal_cursor in connection.cursors)
    assert connection.application_name == "startup-app"
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "SELECT application_name",
        "SET application_name = DEFAULT",
    ]


@pytest.mark.parametrize("first_method", ["execute", "executemany"])
@pytest.mark.parametrize("second_query", ["SELECT second", "COMMIT"])
def test_shared_connection_keeps_set_and_query_together(monkeypatch, first_method, second_query):
    connection = FakeConnection()
    first_cursor = FakePsycopgCursor(connection)
    second_cursor = FakePsycopgCursor(connection)
    first_query_started = threading.Event()
    release_first_query = threading.Event()
    second_query_waiting = threading.Event()

    class FakeConnectionLock:
        def __init__(self):
            self.lock = threading.Lock()

        def __enter__(self):
            if self.lock.locked():
                second_query_waiting.set()
            self.lock.acquire()

        def __exit__(self, *_args):
            self.lock.release()

    connection_lock = FakeConnectionLock()
    monkeypatch.setattr(postgresql, "_get_sync_connection_lock", lambda _connection: connection_lock)

    def before_execute(query):
        if query == "SELECT first":
            first_query_started.set()
            release_first_query.wait(timeout=1)

    connection.before_execute = before_execute

    def run(cursor, method, query, span_context):
        def _fake_traced_execution(_cursor, query_method, *args, **kwargs):
            with trace.use_span(NonRecordingSpan(span_context)):
                return query_method(*args, **kwargs)

        args = (cursor, getattr(cursor, method), query)
        if method == "executemany":
            args += ([()],)
        _execute_with_postgresql_trace_context(_fake_traced_execution, None, args, {})

    first_thread = threading.Thread(target=run, args=(first_cursor, first_method, "SELECT first", DATABASE_CONTEXT))
    second_thread = threading.Thread(target=run, args=(second_cursor, "execute", second_query, SECOND_DATABASE_CONTEXT))
    first_call = ("SELECT first", ()) if first_method == "executemany" else "SELECT first"

    try:
        first_thread.start()
        assert first_query_started.wait(timeout=1)
        second_thread.start()
        assert second_query_waiting.wait(timeout=1)
        assert connection.calls == [
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
            first_call,
        ]
    finally:
        release_first_query.set()
        first_thread.join(timeout=1)
        second_thread.join(timeout=1)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    second_calls = (
        [
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (SECOND_TRACEPARENT,)),
            second_query,
            "SET application_name = DEFAULT",
        ]
        if second_query == "SELECT second"
        else [second_query]
    )
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        first_call,
        "SET application_name = DEFAULT",
        *second_calls,
    ]


class FakeCursorTracer:
    def traced_execution(self, cursor, query_method, *args, **kwargs):
        return _fake_traced_execution(cursor, query_method, *args, **kwargs)

    async def traced_execution_async(self, cursor, query_method, *args, **kwargs):
        return await _fake_traced_execution_async(cursor, query_method, *args, **kwargs)


def test_public_enable_is_idempotent(monkeypatch):
    class CursorTracer(FakeCursorTracer):
        pass

    monkeypatch.setattr(postgresql, "_enabled", False)
    monkeypatch.setattr(postgresql, "import_module", lambda _name: SimpleNamespace(CursorTracer=CursorTracer))
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    assert postgresql.enable_postgresql_trace_context_propagation()
    assert postgresql.enable_postgresql_trace_context_propagation()
    result = CursorTracer().traced_execution(cursor, cursor.execute, "SELECT 1")

    assert result == TRACEPARENT
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "SELECT 1",
        "SET application_name = DEFAULT",
    ]


def test_public_enable_without_dbapi_reports_missing_dependency(monkeypatch, caplog):
    def _fake_dbapi_import(_name):
        raise ImportError

    monkeypatch.setattr(postgresql, "_enabled", False)
    monkeypatch.setattr(postgresql, "import_module", _fake_dbapi_import)

    assert not postgresql.enable_postgresql_trace_context_propagation()
    assert "requires DBAPI instrumentation" in caplog.text


def test_public_enable_clears_context_before_commit_and_raw_queries(monkeypatch):
    class CursorTracer(FakeCursorTracer):
        pass

    monkeypatch.setattr(postgresql, "_enabled", False)
    monkeypatch.setattr(postgresql, "import_module", lambda _name: SimpleNamespace(CursorTracer=CursorTracer))
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    assert postgresql.enable_postgresql_trace_context_propagation()
    assert CursorTracer().traced_execution(cursor, cursor.execute, "SELECT 1") == TRACEPARENT
    assert connection.commit() == "startup-app"
    assert cursor.execute("SELECT untraced") == "startup-app"
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "SELECT 1",
        "SET application_name = DEFAULT",
        "COMMIT",
        "SELECT untraced",
    ]


def test_public_enable_rejects_incompatible_dbapi_before_wrapping(monkeypatch, caplog):
    class CursorTracer:
        def traced_execution(self, cursor, query_method, *args, **kwargs):
            return query_method(*args, **kwargs)

    monkeypatch.setattr(postgresql, "_enabled", False)
    monkeypatch.setattr(postgresql, "import_module", lambda _name: SimpleNamespace(CursorTracer=CursorTracer))
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    assert not postgresql.enable_postgresql_trace_context_propagation()
    CursorTracer().traced_execution(cursor, cursor.execute, "SELECT 1")

    assert connection.calls == ["SELECT 1"]
    assert "compatible DBAPI execution methods" in caplog.text


def test_public_enable_rejects_keyword_only_execution_methods(monkeypatch):
    class CursorTracer:
        def traced_execution(self, *, cursor, query_method):
            return query_method(cursor)

        async def traced_execution_async(self, *, cursor, query_method):
            return await query_method(cursor)

    monkeypatch.setattr(postgresql, "_enabled", False)
    monkeypatch.setattr(postgresql, "import_module", lambda _name: SimpleNamespace(CursorTracer=CursorTracer))

    assert not postgresql.enable_postgresql_trace_context_propagation()


@pytest.mark.parametrize("missing_factory", [False, True])
def test_public_enable_checks_all_factories_before_wrapping(monkeypatch, fake_cursor_adapters, missing_factory):
    class CursorTracer(FakeCursorTracer):
        pass

    original_execution = CursorTracer.traced_execution
    factory_name = "_new_cursor_factory"
    original_factory = getattr(fake_cursor_adapters, factory_name)
    incompatible_module = SimpleNamespace()
    if not missing_factory:
        setattr(incompatible_module, factory_name, lambda wrong_parameter: wrong_parameter)
    adapters = [
        _CursorAdapter(fake_cursor_adapters, "_new_cursor_factory", _FakeDriverCursor, _fake_internal_cursor_factory),
        _CursorAdapter(incompatible_module, "_new_cursor_factory", _FakeDriverCursor, _fake_internal_cursor_factory),
    ]
    monkeypatch.setattr(postgresql, "_enabled", False)
    monkeypatch.setattr(postgresql, "import_module", lambda _name: SimpleNamespace(CursorTracer=CursorTracer))
    monkeypatch.setattr(postgresql, "_load_cursor_adapters", lambda: adapters)

    assert not postgresql.enable_postgresql_trace_context_propagation()
    assert CursorTracer.traced_execution is original_execution
    assert getattr(fake_cursor_adapters, factory_name) is original_factory


@pytest.mark.parametrize("positional_factory", [False, True])
def test_cursor_factory_places_driver_adapter_after_customer_hooks(positional_factory):
    connection = FakeConnection()
    calls = []

    class CustomerCursor(_FakeDriverCursor):
        def execute(self, query):
            calls.append(self.connection.application_name)
            return super().execute(query)

    adapter = _CursorAdapter(None, "_new_cursor_factory", _FakeDriverCursor, _fake_internal_cursor_factory)

    def _fake_instrumentation_cursor_factory(db_api, base_factory):  # noqa: ARG001
        return base_factory

    args = (None, CustomerCursor) if positional_factory else ()
    kwargs = {} if positional_factory else {"db_api": None, "base_factory": CustomerCursor}
    factory = _cursor_factory_wrapper(adapter)(_fake_instrumentation_cursor_factory, None, args, kwargs)
    cursor = factory(connection)
    result = _execute_with_postgresql_trace_context(
        _fake_traced_execution, None, (cursor, cursor.execute, "SELECT 1"), {}
    )

    assert result == TRACEPARENT
    assert calls == ["customer-app"]
    assert isinstance(cursor, CustomerCursor)
    assert connection.calls[-1] == "SET application_name = DEFAULT"


def test_delayed_native_call_cannot_reuse_finished_span_lease():
    async def run():
        connection = FakeConnection()
        cursor = FakePsycopgCursor(connection)
        loop = asyncio.get_running_loop()
        completed = loop.create_future()

        def _execute_uninstrumented_callback():
            completed.set_result(cursor.execute("SELECT delayed"))

        def _fake_schedule_native_callback(query):
            if query == "SELECT outer":
                loop.call_soon(_execute_uninstrumented_callback)

        connection.before_execute = _fake_schedule_native_callback
        assert (
            _execute_with_postgresql_trace_context(
                _fake_traced_execution, None, (cursor, cursor.execute, "SELECT outer"), {}
            )
            == TRACEPARENT
        )
        assert await asyncio.wait_for(completed, timeout=1) == "startup-app"
        assert connection.calls == [
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
            "SELECT outer",
            "SET application_name = DEFAULT",
            "SELECT delayed",
        ]

    asyncio.run(run())


@pytest.mark.parametrize("flags", [0, 1, 2, 3])
def test_query_propagates_valid_context_flags(flags):
    context = SpanContext(
        trace_id=DATABASE_CONTEXT.trace_id,
        span_id=DATABASE_CONTEXT.span_id,
        is_remote=False,
        trace_flags=TraceFlags(flags),
    )
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    def _fake_traced_execution_with_flags(_cursor, query_method, *args, **kwargs):
        with trace.use_span(NonRecordingSpan(context)):
            return query_method(*args, **kwargs)

    result = _execute_with_postgresql_trace_context(
        _fake_traced_execution_with_flags,
        None,
        (cursor, cursor.execute, "SELECT 1"),
        {},
    )

    assert result == f"00-{context.trace_id:032x}-{context.span_id:016x}-{flags:02x}"


def test_failed_internal_command_attempts_customer_query_and_closes_cursor(caplog):
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)

    def _fake_internal_command_failure(query):
        if query.startswith(("SET ", "SELECT pg_catalog.set_config(")):
            message = "SET rejected"
            raise RuntimeError(message)

    connection.before_execute = _fake_internal_command_failure

    result = _execute_with_postgresql_trace_context(
        _fake_traced_execution,
        None,
        (cursor, cursor.execute, "SELECT 1"),
        {},
    )

    assert result == "customer-app"
    assert connection.calls == [
        ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
        "SELECT 1",
        "SET application_name = DEFAULT",
    ]
    assert all(internal_cursor.closed for internal_cursor in connection.cursors)
    assert "Failed to set PostgreSQL application_name" in caplog.text


def test_customer_query_exception_is_returned_to_caller():
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)
    error = RuntimeError("customer query failed")

    def _fake_customer_query_failure(query):
        if query == "SELECT 1":
            raise error

    connection.before_execute = _fake_customer_query_failure

    with pytest.raises(RuntimeError) as raised:
        _execute_with_postgresql_trace_context(
            _fake_traced_execution,
            None,
            (cursor, cursor.execute, "SELECT 1"),
            {},
        )

    assert raised.value is error
    assert connection.calls[-1] == "SET application_name = DEFAULT"
    assert connection.application_name == "startup-app"
    assert all(internal_cursor.closed for internal_cursor in connection.cursors)


@pytest.mark.parametrize("query_fails", [False, True])
def test_failed_cleanup_does_not_replace_customer_result_or_exception(query_fails, caplog):
    connection = FakeConnection()
    cursor = FakePsycopgCursor(connection)
    error = RuntimeError("customer query failed")
    cleanup_error = RuntimeError("cleanup failed")

    def _fake_query_or_cleanup_failure(query):
        if query == "SET application_name = DEFAULT":
            raise cleanup_error
        if query_fails and query == "SELECT 1":
            raise error

    connection.before_execute = _fake_query_or_cleanup_failure
    if query_fails:
        with pytest.raises(RuntimeError) as raised:
            _execute_with_postgresql_trace_context(
                _fake_traced_execution, None, (cursor, cursor.execute, "SELECT 1"), {}
            )
        assert raised.value is error
    else:
        assert (
            _execute_with_postgresql_trace_context(
                _fake_traced_execution, None, (cursor, cursor.execute, "SELECT 1"), {}
            )
            == TRACEPARENT
        )

    assert connection.calls[-1] == "SET application_name = DEFAULT"
    assert all(internal_cursor.closed for internal_cursor in connection.cursors)
    assert "Failed to set PostgreSQL application_name" in caplog.text


@pytest.mark.parametrize("first_method", ["execute", "executemany"])
@pytest.mark.parametrize("second_query", ["SELECT second", "COMMIT"])
def test_async_shared_connection_keeps_set_and_query_together(first_method, second_query):
    async def run():
        connection = FakeAsyncConnection()
        first_query_started = asyncio.Event()
        second_query_started = asyncio.Event()
        release_first_query = asyncio.Event()

        async def _fake_blocking_driver_execute(query):
            if query == "SELECT first":
                first_query_started.set()
                await release_first_query.wait()

        connection.before_execute = _fake_blocking_driver_execute

        async def _fake_second_traced_execution(_cursor, query_method, *args, **kwargs):
            with trace.use_span(NonRecordingSpan(SECOND_DATABASE_CONTEXT)):
                second_query_started.set()
                return await query_method(*args, **kwargs)

        first_cursor = FakeAsyncPsycopgCursor(connection)
        second_cursor = FakeAsyncPsycopgCursor(connection)
        first_args = (first_cursor, getattr(first_cursor, first_method), "SELECT first")
        if first_method == "executemany":
            first_args += ([()],)
        first_call = ("SELECT first", ()) if first_method == "executemany" else "SELECT first"
        first = asyncio.create_task(
            _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async,
                None,
                first_args,
                {},
            )
        )
        second = None
        try:
            await asyncio.wait_for(first_query_started.wait(), timeout=1)
            second = asyncio.create_task(
                _execute_with_postgresql_trace_context_async(
                    _fake_second_traced_execution,
                    None,
                    (second_cursor, second_cursor.execute, second_query),
                    {},
                )
            )
            await asyncio.wait_for(second_query_started.wait(), timeout=1)
            assert connection.calls == [
                ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
                first_call,
            ]
        finally:
            release_first_query.set()
            await asyncio.wait_for(asyncio.gather(*([first, second] if second is not None else [first])), timeout=1)
        second_calls = (
            [
                ("SELECT pg_catalog.set_config('application_name', %s, false)", (SECOND_TRACEPARENT,)),
                second_query,
                "SET application_name = DEFAULT",
            ]
            if second_query == "SELECT second"
            else [second_query]
        )
        assert connection.calls == [
            ("SELECT pg_catalog.set_config('application_name', %s, false)", (TRACEPARENT,)),
            first_call,
            "SET application_name = DEFAULT",
            *second_calls,
        ]

    asyncio.run(run())


def test_async_suppression_sends_only_customer_query():
    async def run():
        connection = FakeAsyncConnection()
        cursor = FakeAsyncPsycopgCursor(connection)
        with suppress_instrumentation():
            await _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async,
                None,
                (cursor, cursor.execute, "SELECT 1"),
                {},
            )
        assert connection.calls == ["SELECT 1"]
        assert connection.cursors == []

    asyncio.run(run())


def test_async_named_cursor_sends_only_customer_query():
    async def run():
        connection = FakeAsyncConnection()
        cursor = FakeAsyncPsycopgCursor(connection)
        cursor.name = "server_cursor"
        result = await _execute_with_postgresql_trace_context_async(
            _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT 1"), {}
        )
        assert result == "customer-app"
        assert connection.calls == ["SELECT 1"]
        assert connection.cursors == []

    asyncio.run(run())


def test_async_customer_cancellation_clears_context_and_releases_connection():
    async def run():
        query_started = asyncio.Event()
        connection = FakeAsyncConnection()

        class BlockingQueryCursor(FakeAsyncPsycopgCursor):
            async def execute(self, query):
                await super().execute(query)
                query_started.set()
                await asyncio.Event().wait()

        cursor = BlockingQueryCursor(connection)
        query = asyncio.create_task(
            _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT 1"), {}
            )
        )
        await asyncio.wait_for(query_started.wait(), timeout=1)
        query.cancel()
        with pytest.raises(asyncio.CancelledError):
            await query

        assert connection.calls[-1] == "SET application_name = DEFAULT"
        assert connection.application_name == "startup-app"
        assert all(internal_cursor.closed for internal_cursor in connection.cursors)
        next_cursor = FakeAsyncPsycopgCursor(connection)
        result = await asyncio.wait_for(
            _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async, None, (next_cursor, next_cursor.execute, "SELECT 2"), {}
            ),
            timeout=1,
        )
        assert result == TRACEPARENT

    asyncio.run(run())


@pytest.mark.parametrize("query_fails", [False, True])
def test_async_failed_cleanup_does_not_replace_customer_result_or_exception(query_fails, caplog):
    async def run():
        connection = FakeAsyncConnection()
        cursor = FakeAsyncPsycopgCursor(connection)
        error = RuntimeError("customer query failed")
        cleanup_error = RuntimeError("cleanup failed")

        def _fake_query_or_cleanup_failure(query):
            if query == "SET application_name = DEFAULT":
                raise cleanup_error
            if query_fails and query == "SELECT 1":
                raise error

        connection.before_execute = _fake_query_or_cleanup_failure
        if query_fails:
            with pytest.raises(RuntimeError) as raised:
                await _execute_with_postgresql_trace_context_async(
                    _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT 1"), {}
                )
            assert raised.value is error
        else:
            result = await _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async, None, (cursor, cursor.execute, "SELECT 1"), {}
            )
            assert result == TRACEPARENT
        assert connection.calls[-1] == "SET application_name = DEFAULT"
        assert all(internal_cursor.closed for internal_cursor in connection.cursors)

    asyncio.run(run())
    assert "Failed to set PostgreSQL application_name" in caplog.text


def test_async_cancellation_closes_internal_cursor_and_releases_connection():
    async def run():
        internal_command_started = asyncio.Event()

        class BlockingInternalCursor(FakeAsyncPsycopgCursor):
            async def execute(self, _query, _parameters=None):
                internal_command_started.set()
                await asyncio.Event().wait()

        class Connection(FakeAsyncConnection):
            def cursor(self):
                if not self.cursors:
                    cursor = BlockingInternalCursor(self)
                    self.cursors.append(cursor)
                    return cursor
                return super().cursor()

        connection = Connection()
        customer_cursor = FakeAsyncPsycopgCursor(connection)
        query = asyncio.create_task(
            _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async,
                None,
                (customer_cursor, customer_cursor.execute, "SELECT 1"),
                {},
            )
        )
        await asyncio.wait_for(internal_command_started.wait(), timeout=1)
        query.cancel()
        with pytest.raises(asyncio.CancelledError):
            await query
        assert connection.cursors[0].closed
        assert customer_cursor.calls == []

        result = await asyncio.wait_for(
            _execute_with_postgresql_trace_context_async(
                _fake_traced_execution_async,
                None,
                (customer_cursor, customer_cursor.execute, "SELECT 2"),
                {},
            ),
            timeout=1,
        )
        assert result == TRACEPARENT

    asyncio.run(run())
