import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from importlib import import_module
from unittest.mock import patch


from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.trace import NonRecordingSpan, SpanContext, SpanKind, TraceFlags


_QUERY = "SELECT current_setting('application_name'), pg_sleep(0.01)"
_DEFAULT_APPLICATION_NAME = "startup-app"


def _traceparent(span) -> str:
    context = span.get_span_context()
    return f"00-{context.trace_id:032x}-{context.span_id:016x}-{int(context.trace_flags) & 0xFF:02x}"


def _assert_database_span(exporter, application_name, parent_context=None):
    matches = [span for span in exporter.get_finished_spans() if _traceparent(span) == application_name]
    assert len(matches) == 1, f"PostgreSQL value {application_name!r} did not identify one exported span"
    span = matches[0]
    assert span.kind == SpanKind.CLIENT
    if parent_context is not None:
        assert span.parent.span_id == parent_context.span_id
        assert span.context.span_id != parent_context.span_id
    return span


def _sync_queries(driver, exporter, tracer):
    with driver.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        for prepared in [False, True, True] if driver.__name__ == "psycopg" else [False]:
            exporter.clear()
            with tracer.start_as_current_span("caller") as parent, connection.cursor() as cursor:
                cursor.execute(_QUERY, **({"prepare": True} if prepared else {}))
                application_name = cursor.fetchone()[0]
            _assert_database_span(exporter, application_name, parent.get_span_context())
            assert len([span for span in exporter.get_finished_spans() if span.kind == SpanKind.CLIENT]) == 1

        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE correlation (application_name text)")
        exporter.clear()
        with connection.cursor() as cursor:
            cursor.executemany("INSERT INTO correlation VALUES (current_setting('application_name'))", [(), ()])
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("SELECT application_name FROM correlation")
            values = [row[0] for row in cursor.fetchall()]
        assert len(values) == 2
        assert values[0] == values[1]
        application_name = values[0]
        _assert_database_span(exporter, values[0])
        assert len(exporter.get_finished_spans()) == 1

        if driver.__name__ == "psycopg2":
            exporter.clear()
            with connection.cursor(name="correlation_cursor") as cursor:
                cursor.execute(_QUERY)
                application_name = cursor.fetchone()[0]
            assert application_name == _DEFAULT_APPLICATION_NAME
            with suppress_instrumentation(), connection.cursor() as cursor:
                cursor.execute(
                    "CREATE FUNCTION pg_temp.correlation_name() RETURNS text LANGUAGE sql "
                    "AS $$ SELECT current_setting('application_name') $$"
                )
            exporter.clear()
            with connection.cursor() as cursor:
                cursor.callproc("pg_temp.correlation_name")
                application_name = cursor.fetchone()[0]
            _assert_database_span(exporter, application_name)

        before = len(exporter.get_finished_spans())
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute(_QUERY)
            assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME
        assert len(exporter.get_finished_spans()) == before


def _sync_concurrency(driver, exporter, tracer):
    with driver.connect() as connection:
        connection.autocommit = True
        exporter.clear()

        def query(_index):
            with tracer.start_as_current_span("concurrent caller") as parent, connection.cursor() as cursor:
                cursor.execute(_QUERY)
                return cursor.fetchone()[0], parent.get_span_context()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(query, range(12)))
        for application_name, parent_context in results:
            _assert_database_span(exporter, application_name, parent_context)
        assert len([span for span in exporter.get_finished_spans() if span.kind == SpanKind.CLIENT]) == 12


async def _async_queries(exporter, tracer):
    import psycopg

    async with await psycopg.AsyncConnection.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        exporter.clear()
        async with connection.cursor() as cursor:
            await cursor.execute(_QUERY, prepare=True)
            application_name = (await cursor.fetchone())[0]
        _assert_database_span(exporter, application_name)
        assert len(exporter.get_finished_spans()) == 1

        with suppress_instrumentation():
            async with connection.cursor() as cursor:
                await cursor.execute("CREATE TEMP TABLE correlation (application_name text)")
        exporter.clear()
        async with connection.cursor() as cursor:
            await cursor.executemany("INSERT INTO correlation VALUES (current_setting('application_name'))", [(), ()])
        with suppress_instrumentation():
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT application_name FROM correlation")
                values = [row[0] for row in await cursor.fetchall()]
        assert len(values) == 2
        assert values[0] == values[1]
        _assert_database_span(exporter, values[0])
        assert len(exporter.get_finished_spans()) == 1

    async with await psycopg.AsyncConnection.connect(
        autocommit=True, application_name=_DEFAULT_APPLICATION_NAME
    ) as connection:
        exporter.clear()

        async def query():
            with tracer.start_as_current_span("async caller") as parent:
                async with connection.cursor() as cursor:
                    await cursor.execute(_QUERY)
                    return (await cursor.fetchone())[0], parent.get_span_context()

        results = await asyncio.wait_for(asyncio.gather(*(query() for _ in range(12))), timeout=10)
        for application_name, parent_context in results:
            _assert_database_span(exporter, application_name, parent_context)
        assert len([span for span in exporter.get_finished_spans() if span.kind == SpanKind.CLIENT]) == 12

        with suppress_instrumentation():
            async with connection.cursor() as cursor:
                await cursor.execute(_QUERY)
                assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME
        assert len([span for span in exporter.get_finished_spans() if span.kind == SpanKind.CLIENT]) == 12

    class RejectingSetCursor(psycopg.AsyncCursor):
        async def execute(self, query, *args, **kwargs):
            if query.startswith("SET application_name"):
                query = "SET nonexistent_correlation_parameter = 'failure'"
            return await super().execute(query, *args, **kwargs)

    connection = await psycopg.AsyncConnection.connect()
    try:
        with patch.object(connection.cursor_factory, "_new_internal_cursor", staticmethod(RejectingSetCursor)):
            async with connection.cursor() as cursor:
                failed = False
                try:
                    await cursor.execute("SELECT 1")
                except psycopg.errors.InFailedSqlTransaction:
                    failed = True
                assert failed
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.INERROR
    finally:
        await connection.close()


def _unsampled_queries(driver, exporter):
    with driver.connect() as connection:
        for flags in (0, 2):
            parent = SpanContext(
                trace_id=0x11111111111111111111111111111111,
                span_id=0x1111111111111111,
                is_remote=True,
                trace_flags=TraceFlags(flags),
            )
            exporter.clear()
            with trace.use_span(NonRecordingSpan(parent)), connection.cursor() as cursor:
                cursor.execute(_QUERY)
                value = cursor.fetchone()[0]
            fields = value.split("-")
            assert fields[1] == f"{parent.trace_id:032x}"
            assert int(fields[2], 16) not in (0, parent.span_id)
            assert int(fields[3], 16) == flags
            assert not exporter.get_finished_spans()


def _reset_to_default(driver):
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
    from opentelemetry.trace import NoOpTracerProvider

    instrumentor = PsycopgInstrumentor if driver.__name__ == "psycopg" else Psycopg2Instrumentor
    with driver.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        with connection.cursor() as cursor:
            cursor.execute(_QUERY)
            assert cursor.fetchone()[0].startswith("00-")
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("SET application_name = 'sql-app'")
        instrumentor.uninstrument_connection(connection)
        instrumentor.instrument_connection(connection, tracer_provider=NoOpTracerProvider())
        with connection.cursor() as cursor:
            cursor.execute(_QUERY)
            assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME


def _failed_internal_command(driver):
    cursor_class = driver.Cursor if driver.__name__ == "psycopg" else driver.extensions.cursor
    transaction_error = driver.errors.InFailedSqlTransaction

    class RejectingSetCursor(cursor_class):
        def execute(self, query, *args, **kwargs):
            if query.startswith("SET application_name"):
                query = "SET nonexistent_correlation_parameter = 'failure'"
            return super().execute(query, *args, **kwargs)

    connection = driver.connect()
    try:
        with (
            patch.object(connection.cursor_factory, "_new_internal_cursor", staticmethod(RejectingSetCursor)),
            connection.cursor() as cursor,
        ):
            try:
                cursor.execute("SELECT 1")
            except transaction_error:
                pass
            else:
                message = "Customer query should report the aborted transaction after failed SET"
                raise AssertionError(message)
        status = (
            connection.info.transaction_status if driver.__name__ == "psycopg" else connection.get_transaction_status()
        )
        assert status == 3
    finally:
        connection.close()

    connection = driver.connect()
    try:
        connection.autocommit = True
        with (
            patch.object(connection.cursor_factory, "_new_internal_cursor", staticmethod(RejectingSetCursor)),
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def _custom_cursor(exporter):
    import psycopg
    import psycopg2
    from psycopg2.extras import RealDictCursor

    for driver, cursor_class in ((psycopg, psycopg.ClientCursor), (psycopg2, RealDictCursor)):
        with driver.connect(cursor_factory=cursor_class) as connection:
            exporter.clear()
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('application_name') AS application_name")
                row = cursor.fetchone()
                application_name = row["application_name"] if isinstance(row, dict) else row[0]
            _assert_database_span(exporter, application_name)


def _nested_cursor_queries(driver, exporter):
    cursor_class = driver.Cursor if driver.__name__ == "psycopg" else driver.extensions.cursor

    class CustomerCursor(cursor_class):
        def execute(self, query, *args, **kwargs):
            if query == _QUERY:
                with self.connection.cursor() as nested:
                    nested.execute("SELECT current_setting('application_name')")
                    self.nested_context = nested.fetchone()[0]
            return super().execute(query, *args, **kwargs)

    for autocommit in (False, True):
        with driver.connect(cursor_factory=CustomerCursor, application_name=_DEFAULT_APPLICATION_NAME) as connection:
            connection.autocommit = autocommit
            exporter.clear()
            with connection.cursor() as cursor:
                cursor.execute(_QUERY)
                outer = _assert_database_span(exporter, cursor.fetchone()[0])
                nested = _assert_database_span(exporter, cursor.nested_context)
            assert nested.parent.span_id == outer.context.span_id
            assert nested.context.span_id != outer.context.span_id
            assert len(exporter.get_finished_spans()) == 2
            with suppress_instrumentation(), connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('application_name')")
                assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME


async def _async_nested_cursor_queries(exporter):
    import psycopg

    class CustomerCursor(psycopg.AsyncCursor):
        async def execute(self, query, *args, **kwargs):
            if query == _QUERY:
                async with self.connection.cursor() as nested:
                    await nested.execute("SELECT current_setting('application_name')")
                    self.nested_context = (await nested.fetchone())[0]
            return await super().execute(query, *args, **kwargs)

    for autocommit in (False, True):
        async with await psycopg.AsyncConnection.connect(
            autocommit=autocommit, cursor_factory=CustomerCursor, application_name=_DEFAULT_APPLICATION_NAME
        ) as connection:
            exporter.clear()
            async with connection.cursor() as cursor:
                await cursor.execute(_QUERY)
                outer = _assert_database_span(exporter, (await cursor.fetchone())[0])
                nested = _assert_database_span(exporter, cursor.nested_context)
            assert nested.parent.span_id == outer.context.span_id
            assert nested.context.span_id != outer.context.span_id
            assert len(exporter.get_finished_spans()) == 2
            with suppress_instrumentation():
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT current_setting('application_name')")
                    assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME


def _transaction_sql(driver, exporter):
    sql = import_module(f"{driver.__name__}.sql")
    statements = (
        ("BEGIN", "COMMIT"),
        ("START TRANSACTION", b"END"),
        (sql.SQL("/* outer /* nested */ comment */ BEGIN"), sql.SQL("COMMIT")),
        ("BEGIN", "ROLLBACK"),
        ("BEGIN", "ABORT"),
    )
    for autocommit in (False, True):
        for begin, end in statements:
            with driver.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
                connection.autocommit = autocommit
                with connection.cursor() as cursor:
                    cursor.execute(begin)
                    exporter.clear()
                    cursor.execute(_QUERY)
                    _assert_database_span(exporter, cursor.fetchone()[0])
                    connection.rollback()
                    with suppress_instrumentation():
                        cursor.execute("SELECT current_setting('application_name')")
                        assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME
                    connection.rollback()

                    cursor.execute(begin)
                    cursor.execute(end)
                    status = (
                        connection.info.transaction_status
                        if driver.__name__ == "psycopg"
                        else connection.get_transaction_status()
                    )
                    assert status == 0
                    if driver.__name__ == "psycopg":
                        connection.autocommit = True
                    with suppress_instrumentation():
                        cursor.execute("SELECT current_setting('application_name')")
                        assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME

                    connection.rollback()
                    connection.autocommit = True
                    cursor.execute("BEGIN; SELECT 1")
                    connection.rollback()
                    cursor.execute("SELECT 1; COMMIT")
                    with suppress_instrumentation():
                        cursor.execute("SELECT current_setting('application_name')")
                        assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME


async def _async_transaction_sql(exporter):
    import psycopg

    statements = (
        ("BEGIN", "COMMIT"),
        ("START TRANSACTION", b"END"),
        (psycopg.sql.SQL("/* outer /* nested */ comment */ BEGIN"), psycopg.sql.SQL("COMMIT")),
        ("BEGIN", "ROLLBACK"),
        ("BEGIN", "ABORT"),
    )
    for autocommit in (False, True):
        for begin, end in statements:
            async with (
                await psycopg.AsyncConnection.connect(
                    autocommit=autocommit, application_name=_DEFAULT_APPLICATION_NAME
                ) as connection,
                connection.cursor() as cursor,
            ):
                await cursor.execute(begin)
                exporter.clear()
                await cursor.execute(_QUERY)
                _assert_database_span(exporter, (await cursor.fetchone())[0])
                await connection.rollback()
                with suppress_instrumentation():
                    await cursor.execute("SELECT current_setting('application_name')")
                    assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME
                await connection.rollback()

                await cursor.execute(begin)
                await cursor.execute(end)
                assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
                await connection.set_autocommit(True)
                with suppress_instrumentation():
                    await cursor.execute("SELECT current_setting('application_name')")
                    assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME

                await cursor.execute("BEGIN; SELECT 1")
                await connection.rollback()
                await cursor.execute("SELECT 1; COMMIT")
                with suppress_instrumentation():
                    await cursor.execute("SELECT current_setting('application_name')")
                    assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME


def _failed_cleanup_command(driver):
    cursor_class = driver.Cursor if driver.__name__ == "psycopg" else driver.extensions.cursor

    class RejectingCleanupCursor(cursor_class):
        def execute(self, query, *args, **kwargs):
            if query == "SET application_name = DEFAULT":
                query = "SET nonexistent_correlation_parameter = 'failure'"
            return super().execute(query, *args, **kwargs)

    connection = driver.connect()
    try:
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE cleanup_failure (value int)")
        connection.commit()
        with (
            patch.object(connection.cursor_factory, "_new_internal_cursor", staticmethod(RejectingCleanupCursor)),
            connection.cursor() as cursor,
        ):
            cursor.execute("INSERT INTO cleanup_failure VALUES (1) RETURNING value")
            assert cursor.fetchone()[0] == 1
        status = (
            connection.info.transaction_status if driver.__name__ == "psycopg" else connection.get_transaction_status()
        )
        assert status == 3
        connection.rollback()
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM cleanup_failure")
            assert cursor.fetchone()[0] == 0
    finally:
        connection.close()


def _parenthesized_queries(driver, exporter):
    with driver.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection, connection.cursor() as cursor:
        for query in (
            "(SELECT current_setting('application_name'))",
            "((SELECT current_setting('application_name'))) UNION (SELECT current_setting('application_name'))",
        ):
            exporter.clear()
            cursor.execute(query)
            _assert_database_span(exporter, cursor.fetchone()[0])
        if driver.__name__ == "psycopg2":
            with suppress_instrumentation():
                cursor.execute(
                    "CREATE FUNCTION begin_job() RETURNS text LANGUAGE sql "
                    "AS $$ SELECT current_setting('application_name') $$"
                )
            exporter.clear()
            cursor.callproc("begin_job")
            _assert_database_span(exporter, cursor.fetchone()[0])
            with suppress_instrumentation():
                cursor.execute("DROP FUNCTION begin_job()")


def _skipped_middle_query(driver, exporter):
    cursor_class = driver.Cursor if driver.__name__ == "psycopg" else driver.extensions.cursor
    inner_values = []

    class CustomerCursor(cursor_class):
        def execute(self, query, *args, **kwargs):
            if query == _QUERY:
                with self.connection.cursor() as middle:
                    middle.execute("SELECT ';'")
                    assert middle.fetchone()[0] == ";"
            elif query == "SELECT ';'":
                with self.connection.cursor() as inner:
                    inner.execute("SELECT current_setting('application_name')")
                    inner_values.append(inner.fetchone()[0])
            return super().execute(query, *args, **kwargs)

    with (
        driver.connect(cursor_factory=CustomerCursor, application_name=_DEFAULT_APPLICATION_NAME) as connection,
        connection.cursor() as cursor,
    ):
        exporter.clear()
        cursor.execute(_QUERY)
        outer = _assert_database_span(exporter, cursor.fetchone()[0])
        inner = _assert_database_span(exporter, inner_values[0])
        assert inner.context.span_id != outer.context.span_id


def _custom_commit_before_query(driver, exporter):
    cursor_class = driver.Cursor if driver.__name__ == "psycopg" else driver.extensions.cursor

    class CustomerCursor(cursor_class):
        def execute(self, query, *args, **kwargs):
            if query == _QUERY:
                with self.connection.cursor() as auxiliary:
                    auxiliary.execute("COMMIT")
                status = (
                    self.connection.info.transaction_status
                    if driver.__name__ == "psycopg"
                    else self.connection.get_transaction_status()
                )
                assert status == 0
            return super().execute(query, *args, **kwargs)

    for autocommit in (False, True):
        with driver.connect(cursor_factory=CustomerCursor, application_name=_DEFAULT_APPLICATION_NAME) as connection:
            connection.autocommit = autocommit
            exporter.clear()
            with connection.cursor() as cursor:
                cursor.execute(_QUERY)
                _assert_database_span(exporter, cursor.fetchone()[0])
                connection.rollback()
                with suppress_instrumentation():
                    cursor.execute("SELECT current_setting('application_name')")
                    assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME


async def _delayed_sync_callback(driver, exporter):
    cursor_class = driver.Cursor if driver.__name__ == "psycopg" else driver.extensions.cursor
    loop = asyncio.get_running_loop()
    completed = loop.create_future()

    def _execute_delayed_query(connection):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('application_name')")
                completed.set_result(cursor.fetchone()[0])
        except (AssertionError, driver.Error) as error:
            completed.set_exception(error)

    class CustomerCursor(cursor_class):
        def execute(self, query, *args, **kwargs):
            if query == _QUERY:
                loop.call_soon(_execute_delayed_query, self.connection)
            return super().execute(query, *args, **kwargs)

    with driver.connect(cursor_factory=CustomerCursor, application_name=_DEFAULT_APPLICATION_NAME) as connection:
        exporter.clear()
        with connection.cursor() as cursor:
            cursor.execute(_QUERY)
            outer = _assert_database_span(exporter, cursor.fetchone()[0])
        delayed = _assert_database_span(exporter, await asyncio.wait_for(completed, timeout=5))
        assert delayed.context.span_id != outer.context.span_id
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('application_name')")
            assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME


async def _async_driver_regressions(exporter):
    import psycopg

    inner_values = []

    class CustomerCursor(psycopg.AsyncCursor):
        async def execute(self, query, *args, **kwargs):
            if query == _QUERY:
                async with self.connection.cursor() as middle:
                    await middle.execute("SELECT ';'")
                    assert (await middle.fetchone())[0] == ";"
            elif query == "SELECT ';'":
                async with self.connection.cursor() as inner:
                    await inner.execute("SELECT current_setting('application_name')")
                    inner_values.append((await inner.fetchone())[0])
            elif query == "SELECT current_setting('application_name') AS after_commit":
                async with self.connection.cursor() as auxiliary:
                    await auxiliary.execute("COMMIT")
                assert self.connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            return await super().execute(query, *args, **kwargs)

    for autocommit in (False, True):
        async with (
            await psycopg.AsyncConnection.connect(
                autocommit=autocommit, cursor_factory=CustomerCursor, application_name=_DEFAULT_APPLICATION_NAME
            ) as connection,
            connection.cursor() as cursor,
        ):
            for query in (
                "(SELECT current_setting('application_name'))",
                "((SELECT current_setting('application_name'))) UNION (SELECT current_setting('application_name'))",
                _QUERY,
                "SELECT current_setting('application_name') AS after_commit",
            ):
                exporter.clear()
                inner_values.clear()
                await cursor.execute(query)
                outer = _assert_database_span(exporter, (await cursor.fetchone())[0])
                if inner_values:
                    inner = _assert_database_span(exporter, inner_values[0])
                    assert inner.context.span_id != outer.context.span_id
                await connection.rollback()
                with suppress_instrumentation():
                    await cursor.execute("SELECT current_setting('application_name')")
                    assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME
                await connection.rollback()


def _manual_custom_cursor(exporter):
    import psycopg
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    hook_queries = []

    class CustomerCursor(psycopg.Cursor):
        def execute(self, query, *args, **kwargs):
            hook_queries.append(query)
            return super().execute(query, *args, **kwargs)

    with psycopg.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        connection.cursor_factory = CustomerCursor
        PsycopgInstrumentor().instrument_connection(connection)
        instrumented_factory = connection.cursor_factory
        PsycopgInstrumentor().instrument_connection(connection)
        assert connection.cursor_factory is instrumented_factory
        exporter.clear()
        with connection.cursor() as cursor:
            cursor.execute(_QUERY)
            _assert_database_span(exporter, cursor.fetchone()[0])
        assert hook_queries == [_QUERY]
        PsycopgInstrumentor().uninstrument_connection(connection)
        assert connection.cursor_factory is CustomerCursor
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('application_name')")
            assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME


async def _async_manual_custom_cursor(exporter):
    import psycopg
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    hook_queries = []

    class CustomerCursor(psycopg.AsyncCursor):
        async def execute(self, query, *args, **kwargs):
            hook_queries.append(query)
            return await super().execute(query, *args, **kwargs)

    async with await psycopg.AsyncConnection.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        connection.cursor_factory = CustomerCursor
        PsycopgInstrumentor().instrument_connection(connection)
        instrumented_factory = connection.cursor_factory
        PsycopgInstrumentor().instrument_connection(connection)
        assert connection.cursor_factory is instrumented_factory
        exporter.clear()
        async with connection.cursor() as cursor:
            await cursor.execute(_QUERY)
            _assert_database_span(exporter, (await cursor.fetchone())[0])
        assert hook_queries == [_QUERY]
        PsycopgInstrumentor().uninstrument_connection(connection)
        assert connection.cursor_factory is CustomerCursor
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT current_setting('application_name')")
            assert (await cursor.fetchone())[0] == _DEFAULT_APPLICATION_NAME


def _psycopg_server_cursor_boundary(exporter):
    import psycopg

    with psycopg.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        with connection.cursor() as cursor:
            cursor.execute(_QUERY)
            earlier_context = cursor.fetchone()[0]
        exporter.clear()
        with connection.cursor(name="raw_server_cursor") as cursor:
            cursor.execute(_QUERY)
            assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME
            assert earlier_context != _DEFAULT_APPLICATION_NAME
        assert not exporter.get_finished_spans()


def _psycopg2_commit_boundary(exporter):
    import psycopg2

    connection = psycopg2.connect(application_name=_DEFAULT_APPLICATION_NAME)
    try:
        exporter.clear()
        with connection, connection.cursor() as cursor:
            cursor.execute(_QUERY)
            _assert_database_span(exporter, cursor.fetchone()[0])
            assert connection.get_parameter_status("application_name") == _DEFAULT_APPLICATION_NAME

        assert not connection.closed
        assert connection.get_parameter_status("application_name") == _DEFAULT_APPLICATION_NAME
        with suppress_instrumentation(), connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('application_name')")
            assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME
        connection.rollback()
        assert connection.get_parameter_status("application_name") == _DEFAULT_APPLICATION_NAME
    finally:
        connection.close()


async def _async_query_cancellation():
    import psycopg

    async with await psycopg.AsyncConnection.connect(autocommit=True) as observer:
        for autocommit in (False, True):
            async with (
                await psycopg.AsyncConnection.connect(
                    autocommit=autocommit, application_name=_DEFAULT_APPLICATION_NAME
                ) as connection,
                connection.cursor() as cursor,
            ):
                query = asyncio.create_task(cursor.execute("SELECT pg_sleep(10)"))
                try:
                    with suppress_instrumentation():
                        async with observer.cursor() as observer_cursor:
                            for _ in range(20):
                                await observer_cursor.execute(
                                    "SELECT state, query FROM pg_stat_activity WHERE pid = %s",
                                    (connection.info.backend_pid,),
                                )
                                state, statement = await observer_cursor.fetchone()
                                if state == "active" and statement == "SELECT pg_sleep(10)":
                                    break
                                await asyncio.sleep(0.05)
                            assert state == "active", "Customer query did not start before cancellation"
                            assert statement == "SELECT pg_sleep(10)"
                finally:
                    query.cancel()
                    with suppress(asyncio.CancelledError):
                        await query

                if not autocommit:
                    assert connection.info.transaction_status == psycopg.pq.TransactionStatus.INERROR
                    await connection.rollback()
                assert connection.info.parameter_status("application_name") == _DEFAULT_APPLICATION_NAME
                with suppress_instrumentation():
                    await cursor.execute("SELECT 1")
                    assert (await cursor.fetchone())[0] == 1


def run_regressions(exporter, tracer):
    import psycopg
    import psycopg2
    from splunk_otel.postgresql import enable_postgresql_trace_context_propagation

    assert enable_postgresql_trace_context_propagation()
    assert enable_postgresql_trace_context_propagation()
    for driver in (psycopg, psycopg2):
        _sync_queries(driver, exporter, tracer)
        _sync_concurrency(driver, exporter, tracer)
        _unsampled_queries(driver, exporter)
        _reset_to_default(driver)
        _failed_internal_command(driver)
        _failed_cleanup_command(driver)
        _nested_cursor_queries(driver, exporter)
        _transaction_sql(driver, exporter)
        _parenthesized_queries(driver, exporter)
        _skipped_middle_query(driver, exporter)
        _custom_commit_before_query(driver, exporter)
        asyncio.run(_delayed_sync_callback(driver, exporter))
    asyncio.run(_async_queries(exporter, tracer))
    asyncio.run(_async_nested_cursor_queries(exporter))
    asyncio.run(_async_transaction_sql(exporter))
    asyncio.run(_async_driver_regressions(exporter))
    _custom_cursor(exporter)
    _manual_custom_cursor(exporter)
    asyncio.run(_async_manual_custom_cursor(exporter))
    _psycopg_server_cursor_boundary(exporter)
    _psycopg2_commit_boundary(exporter)
    asyncio.run(_async_query_cancellation())
