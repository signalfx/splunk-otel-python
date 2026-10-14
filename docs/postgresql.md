# PostgreSQL trace correlation

This experimental feature connects sampled PostgreSQL queries in Splunk Database
Monitoring to the APM trace and database client span that executed them. It places
the database client span's W3C `traceparent` in PostgreSQL's `application_name`.
It sends only `traceparent`, without baggage or `tracestate`. Valid unsampled
span contexts also work.

## Database Monitoring prerequisites

Configure a Collector with the PostgreSQL receiver, database monitoring
permissions, and both `db.server.query_sample` and `db.server.top_query` enabled.
Export database metrics and query events to Splunk Database Monitoring. Query
events use `/v3/event` with the `X-splunk-instrumentation-library: dbmon` header.
See the [PostgreSQL receiver setup instructions](https://help.splunk.com/en/splunk-observability-cloud/monitor-databases/get-data-in/configure-receivers/postgresql-receiver).

The receiver must support extracting trace and span IDs from `application_name`.
End-to-end correlation was validated with Splunk Collector 0.162.0. The minimum
compatible Collector version has not yet been established for this feature.
The application must also export traces to APM in the same organization; those
traces can use a separate export path. A query sample can link to a trace only
when that trace is available in APM.

## Enablement

The feature is disabled by default. In the same Python environment as your
application, install `splunk-opentelemetry` and your application's PostgreSQL
driver first. Then install instrumentation for the installed libraries:

```sh
opentelemetry-bootstrap -a install
```

This command selects instrumentation versions that match the installed distro.
For PostgreSQL, it installs:

| Application driver | Instrumentation package |
|---|---|
| `psycopg` (Psycopg 3) | [opentelemetry-instrumentation-psycopg](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg/psycopg.html) |
| `psycopg2` or `psycopg2-binary` | [opentelemetry-instrumentation-psycopg2](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html) |

Start the application with:

```sh
SPLUNK_POSTGRESQL_TRACE_CONTEXT_PROPAGATION_ENABLED=true \
opentelemetry-instrument python app.py
```

The environment switch applies when `OTEL_CONFIG_FILE` is unset. Activation lasts
for the process lifetime. To turn it off, unset the switch and restart.

Manual instrumentation must initialize the Splunk distro first with
`init_splunk_otel()`, or call
`splunk_otel.postgresql.enable_postgresql_trace_context_propagation()` before using
`PsycopgInstrumentor` or `Psycopg2Instrumentor`.

## Driver coverage

The feature targets Psycopg 3 synchronous and asynchronous connections and
Psycopg2 synchronous connections. Psycopg2 asynchronous connections pass through
without trace propagation.

Named/server cursors, cursor fetch operations, and COPY operations are outside
this feature's automatic coverage. Named cursors can execute SQL later during
fetch, after the execute span has ended, so this feature skips propagation for
them in both drivers.

## Connection behavior

The feature uses a separate cursor on the same connection for internal commands
and suppresses instrumentation for those commands. A per-connection lock covers
SET, the customer query, and cleanup. Each traced query sends two additional
commands: SET before execution and SET DEFAULT afterward.

This opt-in owns the connection's `application_name` during execution. Cleanup
resets the setting to the connection's configured default before releasing the
instrumentation lock, including when the query raises an exception. If
instrumentation creates no valid new database span, the feature sends SET DEFAULT
before execution. It does not restore a value that the application previously
set through SQL.

The lock only coordinates wrapped queries. Raw cursors and suppressed queries
can bypass it and observe another query's context during execution. Failed
cleanup can also leave trace context set until the application recovers the
connection or rolls back its transaction.

## Failure behavior and query duration

The feature logs internal command failures and attempts the customer query. A
failed setup command can leave a transaction aborted, so the customer query can
also fail. Cleanup failures do not replace the customer query's result or error;
they can still leave an otherwise successful transaction aborted. The feature
does not roll back application transactions.

The extra commands add latency. Database span duration and database operation
duration metrics include lock waiting and the additional commands.
