import asyncio
import json
import os
import re
from importlib.metadata import version
from pathlib import Path


_QUERY = "SELECT current_setting('application_name')"
_DEFAULT_APPLICATION_NAME = "startup-app"
_RESULT_PREFIX = "POSTGRESQL_QUERY_RESULT "
_DRIVERS = {"psycopg", "psycopg2", "psycopg-async"}


def _print_query_result(driver, application_name, parent):
    context = parent.get_span_context()
    print(  # noqa: T201
        _RESULT_PREFIX
        + json.dumps(
            {
                "driver": driver,
                "application_name": application_name,
                "parent_trace_id": f"{context.trace_id:032x}",
                "parent_span_id": f"{context.span_id:016x}",
            }
        ),
        flush=True,
    )


def _sync_query(driver, tracer):
    with (
        driver.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection,
        tracer.start_as_current_span(f"{driver.__name__} caller") as parent,
        connection.cursor() as cursor,
    ):
        cursor.execute(_QUERY)
        application_name = cursor.fetchone()[0]
    _print_query_result(driver.__name__, application_name, parent)


async def _async_query(tracer):
    import psycopg

    async with await psycopg.AsyncConnection.connect(application_name=_DEFAULT_APPLICATION_NAME) as connection:
        with tracer.start_as_current_span("psycopg async caller") as parent:
            async with connection.cursor() as cursor:
                await cursor.execute(_QUERY)
                application_name = (await cursor.fetchone())[0]
    _print_query_result("psycopg-async", application_name, parent)


def main():
    from opentelemetry import trace

    mode = os.environ["POSTGRESQL_TEST_INSTRUMENTATION"]
    if mode == "manual":
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        from splunk_otel import init_splunk_otel

        init_splunk_otel()
        PsycopgInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()

    import psycopg
    import psycopg2

    tracer = trace.get_tracer(__name__)
    for driver in (psycopg, psycopg2):
        _sync_query(driver, tracer)
    asyncio.run(_async_query(tracer))

    if mode != "disabled":
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from regressions import run_regressions

        # Keep per-query regression checks alongside normal OTLP export.
        exporter = InMemorySpanExporter()
        trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
        run_regressions(exporter, tracer)

    if not trace.get_tracer_provider().force_flush():
        message = "PostgreSQL test traces did not finish exporting"
        raise RuntimeError(message)
    print(  # noqa: T201
        f"POSTGRESQL_CORRELATION_OK mode={mode} psycopg={version('psycopg')} "
        f"psycopg2={version('psycopg2-binary')} instrumentation={version('opentelemetry-instrumentation')}"
    )


class PostgreSQLTraceContextOtelTest:
    def __init__(self):
        self.mode = os.environ.get("POSTGRESQL_TEST_INSTRUMENTATION", "auto")
        if self.mode not in {"auto", "manual", "disabled"}:
            message = f"Unknown PostgreSQL test instrumentation mode: {self.mode}"
            raise ValueError(message)

    def requirements(self):
        return (
            str(Path(__file__).resolve().parents[3]),
            "psycopg[binary]",
            "psycopg2-binary",
            "opentelemetry-instrumentation-psycopg",
            "opentelemetry-instrumentation-psycopg2",
        )

    def environment_variables(self):
        return {
            "POSTGRESQL_TEST_INSTRUMENTATION": self.mode,
            "SPLUNK_DB_TRACE_CONTEXT_PROPAGATION_ENABLED": str(self.mode != "disabled").lower(),
            "SPLUNK_OPAMP_ENABLED": "false",
            "OTEL_SERVICE_NAME": "postgresql-trace-context-test",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_TRACES_SAMPLER": "parentbased_always_on",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4317",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_LOGS_EXPORTER": "none",
            "PGHOST": os.environ.get("PGHOST", "127.0.0.1"),
            "PGPORT": os.environ.get("PGPORT", "5432"),
            "PGDATABASE": os.environ.get("PGDATABASE", "otel"),
            "PGUSER": os.environ.get("PGUSER", "otel"),
            "PGPASSWORD": os.environ.get("PGPASSWORD", "otel"),
        }

    def wrapper_command(self):
        return "" if self.mode == "manual" else "opentelemetry-instrument"

    def is_http(self):
        return False

    def on_start(self):
        return 120

    def on_stop(self, telemetry, stdout: str, stderr: str, returncode: int) -> None:
        from opentelemetry.proto.trace.v1.trace_pb2 import Span
        from oteltest.telemetry import get_spans

        # oteltest 0.49 logs AssertionError without failing its command.
        if returncode != 0:
            message = f"PostgreSQL test exited with {returncode}.\nstdout: {stdout}\nstderr: {stderr}"
            raise RuntimeError(message)
        results = [
            json.loads(line.removeprefix(_RESULT_PREFIX))
            for line in stdout.splitlines()
            if line.startswith(_RESULT_PREFIX)
        ]
        if len(results) != len(_DRIVERS) or {result["driver"] for result in results} != _DRIVERS:
            message = "Missing PostgreSQL query results"
            raise RuntimeError(message)

        spans = get_spans(telemetry)
        for result in results:
            matches = [
                span
                for span in spans
                if span.kind == Span.SPAN_KIND_CLIENT
                and span.trace_id.hex() == result["parent_trace_id"]
                and span.parent_span_id.hex() == result["parent_span_id"]
            ]
            if len(matches) != 1:
                message = f"Expected one exported database CLIENT span for {result['driver']}, got {len(matches)}"
                raise RuntimeError(message)
            span = matches[0]
            expected = (
                _DEFAULT_APPLICATION_NAME
                if self.mode == "disabled"
                else rf"00-{span.trace_id.hex()}-{span.span_id.hex()}-[0-9a-f]{{2}}"
            )
            # Some OTLP exporters omit traceparent flag bits; compare the IDs.
            if re.fullmatch(expected, result["application_name"]) is None:
                message = f"PostgreSQL application_name did not match the exported span for {result['driver']}"
                raise RuntimeError(message)


if __name__ == "__main__":
    main()
