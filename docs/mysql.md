# Experimental MySQL query correlation

The goal is to link a query in Database Monitoring (DBMon) to the application
trace that caused it. A trace describes an application request. A span describes
one operation within that request, such as a database call.

## How the link works

Before running a query, we store the trace and database span IDs in a MySQL
session variable named `@traceparent`. A session variable belongs to one database
connection and keeps its value until it is changed or the session is cleared.

`traceparent` is an ordinary variable name to MySQL. Our code and the Collector
agree to use that name. The value follows the standard W3C `traceparent` format:

```sql
SET @traceparent = '00-<trace-id>-<span-id>-<flags>';
```

The Collector reads this variable when it samples queries. DBMon can then use
the IDs to link a sampled query to its application trace. We still need to test
that full path with this implementation.

## What is implemented

`splunk_otel.mysql.execute_with_trace_context` does three things:

1. Writes the supplied database span's context to `@traceparent`.
2. Calls the supplied query method once.
3. Attempts to clear `@traceparent` with `SET @traceparent = NULL`, even if the
   query fails.

Clearing the variable prevents a later operation from inheriting the completed
query's IDs. The helper uses a separate cursor for its SET commands and disables
tracing around those commands so they do not create extra spans.

The helper uses only the span context supplied by its caller. Valid IDs are
written even when the trace is not selected for export. If the supplied context
is invalid, the helper clears the variable before the query. It does not use the
surrounding application's span instead.

## Connector/Python integration

Call `enable_mysql_trace_context_propagation()` explicitly to install the
process-lifetime hook. It returns `False` and logs a warning if Connector/Python
or compatible OpenTelemetry DBAPI instrumentation is unavailable. Repeated calls
do not install additional wrappers. There is no startup activation or environment
setting yet.

```python
import mysql.connector
from opentelemetry.instrumentation.mysql import MySQLInstrumentor
from splunk_otel.mysql import enable_mysql_trace_context_propagation

assert enable_mysql_trace_context_propagation()
MySQLInstrumentor().instrument()

with mysql.connector.connect(database="example", buffered=True) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        rows = cursor.fetchall()
```

Configure an OpenTelemetry tracer provider before running this example. The hook
also works with connections wrapped by `MySQLInstrumentor.instrument_connection()`.
It uses the database span created by OpenTelemetry and adds no spans for its
internal SET commands. Suppressed calls and no-op tracers clear the variable for
eligible queries without copying an application parent span.

The first integration supports Connector/Python's built-in buffered tuple,
raw, and dictionary cursors, in pure Python and C extension modes. Before adding
session commands, the hook requires all of the following:

- The cursor uses the built-in `execute` method and a built-in physical connection.
- The connection reports no unread rows or additional result sets.
- The SQL is a string beginning with `SELECT`, `INSERT`, `UPDATE`, `DELETE`,
  `REPLACE`, `WITH`, `SHOW`, `EXPLAIN`, `DESCRIBE`, or `DESC` followed by whitespace.
- The SQL contains no semicolons except an optional final terminator, no comment
  markers (`/*`, `--`, or `#`), no NUL character, and no `DELIMITER` word.

The SQL check is deliberately conservative. It also skips markers inside quoted
strings. SQLCommenter adds comments to queries, so those queries are skipped.
Stored-procedure calls, scripts, batches, prepared cursors, unbuffered cursors,
custom cursor and connection subclasses, bytes SQL, other drivers, and asynchronous
calls run through their existing instrumentation without correlation commands.
Skipped calls do not clear an existing session value.

Connections must not be shared by concurrent calls. The hook depends on the
DBAPI execution callback and Connector/Python cursor connection reference, which
are private interfaces. The tested versions are DBAPI instrumentation 0.66b1 and
Connector/Python 26.7.0; other versions need separate validation.

## Direct helper calls

The helper requires the actual driver connection, without an instrumentation
wrapper, and the context of the span for this database call. It does not create
that span itself.

The connection must have no pending results from earlier queries. The query must
return at most one result set and use a buffered cursor: the driver downloads all
rows before the query method returns. MySQL may reject the cleanup SET if rows
are still waiting to be downloaded.

Direct helper calls must meet these restrictions themselves. The Connector/Python
hook checks its supported cursor types, connection state, and SQL before calling
the helper.

## Validation

The driver tests use a disposable MySQL database. Install the project, pytest,
`mysql-connector-python==26.7.0`, and
`opentelemetry-instrumentation-mysql==0.66b1` into a virtual environment. Start a
test server, then run the tests from the repository root:

```sh
docker run --detach --rm --name mysql-correlation-tests \
  --env MYSQL_ROOT_PASSWORD=prototype-only --env MYSQL_DATABASE=correlation \
  --publish 127.0.0.1:33060:3306 mysql:8.4
# Wait until mysqladmin reports that the server is alive.
docker exec --env MYSQL_PWD=prototype-only mysql-correlation-tests \
  mysqladmin --protocol=tcp --host=127.0.0.1 --user=root ping --silent
MYSQL_CORRELATION_TEST_PORT=33060 python -m pytest \
  tests/test_mysql.py tests/integration/mysql/test_correlation.py -q
docker stop mysql-correlation-tests
```

The driver tests skip when the port variable or optional packages are absent.
They check exact child-span IDs, buffered rows after cleanup, error recovery,
suppression, unsampled spans, transaction boundaries, and unsupported query paths
against MySQL 8.4.11 in both driver modes. They do not validate Collector or DBMon.

## Failures and remaining work

If an internal SET command fails, the helper logs a warning. It still returns the
query's result or raises the query's original exception. A failed SET can leave
old IDs on the connection, so later queries could receive an incorrect trace
link.

Every eligible query adds two SET commands. These commands also change MySQL
session diagnostics, such as `ROW_COUNT()` and the warning list. Applications
that depend on the previous command's diagnostics need further design work.

The remaining work includes startup configuration, connection-pool validation,
streaming results, multiple result sets, custom cursors, additional drivers,
asynchronous drivers, overhead measurement, and Collector/DBMon testing.
