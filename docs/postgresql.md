# PostgreSQL trace correlation

This experimental feature lets Splunk Database Monitoring link PostgreSQL query
samples to APM traces. It puts the database span's trace and span IDs in
PostgreSQL's `application_name` while a query runs.

## Setup

Configure the [PostgreSQL receiver](https://help.splunk.com/en/splunk-observability-cloud/monitor-databases/get-data-in/configure-receivers/postgresql-receiver)
with `db.server.query_sample` and `db.server.top_query` enabled. The receiver must
read trace IDs from `application_name`; Splunk Collector 0.162.0 was tested.
Send database metrics, query events, and application traces to the same Splunk
organization. A query sample can link to a trace only if APM has that trace.

Install `splunk-opentelemetry` and your PostgreSQL driver in the application's
Python environment. Then run:

```sh
opentelemetry-bootstrap -a install
SPLUNK_DB_TRACE_CONTEXT_PROPAGATION_ENABLED=true \
opentelemetry-instrument python app.py
```

The feature is off by default. The setting works when `OTEL_CONFIG_FILE` is unset.
To turn it off, unset the setting and restart the application.

For manual instrumentation, call `init_splunk_otel()` before using
`PsycopgInstrumentor` or `Psycopg2Instrumentor` and before creating connections.
You can also enable it directly with
`splunk_otel.postgresql.enable_postgresql_trace_context_propagation()`.

## Supported queries

The feature supports Psycopg 3 sync and async connections and Psycopg2 sync
connections. Python 3.14 template queries require Psycopg 3.3 or later.
Custom cursor methods must call the driver method through `super()`.

The feature skips:

- Psycopg2 async connections and Psycopg 3 queries inside explicit pipelines.
- Named/server cursors, fetch operations, and COPY.
- SQL transaction commands, such as BEGIN, COMMIT, ROLLBACK, and SAVEPOINT.
- Transaction settings, such as SET TRANSACTION (including SNAPSHOT),
  SET SESSION CHARACTERISTICS, and SET [SESSION | LOCAL] transaction_isolation,
  transaction_read_only, or transaction_deferrable.
- SQL CALL, DO, and query batches. Any semicolon except one at the end causes
  the query to be skipped, even inside a string or comment.

Standalone `executemany` is supported. Queries in a pipeline still get normal
tracing, but no correlation commands. Correlation resumes after the pipeline exits.

## Connection changes and cost

Each correlated query adds two database commands: one to set `application_name`
and one to reset it. The set command uses parameters, so each new trace ID does
not create a separate `pg_stat_statements` entry.

After the query, the feature resets `application_name` to the connection's
configured default. It does not restore a value the application set through SQL.

Queries that use this feature share a lock on the connection. Raw cursors and
queries with instrumentation suppressed can bypass the lock and see another
query's trace IDs. Span duration includes lock waiting and the extra commands.

The feature logs failures in its own commands. A failed command can abort the
application's transaction or leave trace IDs in `application_name`. The
application must handle recovery; the feature does not roll back transactions.
Cleanup errors do not replace the application's query result or error.

## Tests

Tested with PostgreSQL 16, Psycopg 3.3.6, Psycopg2 2.9.13, and OpenTelemetry
instrumentation 0.66b1. Other versions have not been validated.

To run the integration tests, start PostgreSQL with `pg_stat_statements` preloaded
and utility tracking enabled. Install `oteltest>=0.49.0`, then run:

```sh
PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=otel PGUSER=otel PGPASSWORD=otel \
POSTGRESQL_TEST_INSTRUMENTATION=auto \
oteltest tests/integration/postgresql/trace_context.py
```

Repeat with `POSTGRESQL_TEST_INSTRUMENTATION=manual` and `disabled`.
