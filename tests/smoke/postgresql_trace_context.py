import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version


os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "system_metrics")
os.environ.setdefault("OTEL_SERVICE_NAME", "postgresql-trace-context-smoke-test")
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_TRACES_SAMPLER", "parentbased_always_on")
os.environ.setdefault("SPLUNK_OPAMP_ENABLED", "false")
os.environ.setdefault("SPLUNK_POSTGRESQL_TRACE_CONTEXT_PROPAGATION_ENABLED", "true")
os.environ.setdefault("PGHOST", "127.0.0.1")
os.environ.setdefault("PGPORT", "5432")
os.environ.setdefault("PGDATABASE", "otel")
os.environ.setdefault("PGUSER", "otel")
os.environ.setdefault("PGPASSWORD", "otel")

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
            _assert_database_span(exporter, application_name)
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
            assert cursor.fetchone()[0] == application_name
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

    async with await psycopg.AsyncConnection.connect() as connection:
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

    async with await psycopg.AsyncConnection.connect(autocommit=True) as connection:
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
                assert (await cursor.fetchone())[0] == results[-1][0]
        assert len([span for span in exporter.get_finished_spans() if span.kind == SpanKind.CLIENT]) == 12

    class RejectingSetCursor(psycopg.AsyncCursor):
        async def execute(self, query, *args, **kwargs):
            if query.startswith("SET application_name"):
                query = "SET nonexistent_correlation_parameter = 'failure'"
            return await super().execute(query, *args, **kwargs)

    connection = await psycopg.AsyncConnection.connect(cursor_factory=RejectingSetCursor)
    try:
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

    connection = driver.connect(cursor_factory=RejectingSetCursor)
    try:
        with connection.cursor() as cursor:
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

    connection = driver.connect(cursor_factory=RejectingSetCursor)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
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


def _psycopg_server_cursor_boundary(exporter):
    import psycopg

    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(_QUERY)
            earlier_context = cursor.fetchone()[0]
        exporter.clear()
        with connection.cursor(name="raw_server_cursor") as cursor:
            cursor.execute(_QUERY)
            assert cursor.fetchone()[0] == earlier_context
        assert not exporter.get_finished_spans()


def main():
    from opentelemetry.instrumentation.auto_instrumentation import initialize
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from splunk_otel import init_splunk_otel
    from splunk_otel.postgresql import enable_postgresql_trace_context_propagation

    mode = os.environ.get("POSTGRESQL_SMOKE_INSTRUMENTATION", "auto")
    if mode == "manual":
        init_splunk_otel()
        PsycopgInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
    else:
        initialize(swallow_exceptions=False)

    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    tracer = trace.get_tracer(__name__)

    import psycopg
    import psycopg2

    if mode == "disabled":
        for driver in (psycopg, psycopg2):
            with (
                driver.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(_QUERY)
                assert cursor.fetchone()[0] == _DEFAULT_APPLICATION_NAME
    else:
        assert enable_postgresql_trace_context_propagation()
        assert enable_postgresql_trace_context_propagation()
        for driver in (psycopg, psycopg2):
            _sync_queries(driver, exporter, tracer)
            _sync_concurrency(driver, exporter, tracer)
            _unsampled_queries(driver, exporter)
            _reset_to_default(driver)
            _failed_internal_command(driver)
        asyncio.run(_async_queries(exporter, tracer))
        _custom_cursor(exporter)
        _psycopg_server_cursor_boundary(exporter)

    print(  # noqa: T201
        f"POSTGRESQL_CORRELATION_OK mode={mode} psycopg={version('psycopg')} "
        f"psycopg2={version('psycopg2-binary')} instrumentation={version('opentelemetry-instrumentation')}"
    )


if __name__ == "__main__":
    main()
