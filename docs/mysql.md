# MySQL query correlation: first implementation step

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

## What the caller must provide

The helper requires the actual driver connection, without an instrumentation
wrapper, and the context of the span for this database call. It does not create
that span itself.

The connection must have no pending results from earlier queries. The query must
return at most one result set and use a buffered cursor: the driver downloads all
rows before the query method returns. MySQL may reject the cleanup SET if rows
are still waiting to be downloaded.

The helper does not check these restrictions yet. Driver integration must enforce
them before the helper can be used automatically.

## Failures and remaining work

If an internal SET command fails, the helper logs a warning. It still returns the
query's result or raises the query's original exception. A failed SET can leave
old IDs on the connection, so later queries could receive an incorrect trace
link.

This is an experimental building block. It is not enabled at startup and has no
environment setting. The remaining work includes driver integration, transaction
and connection-pool handling, streaming results, multiple result sets, custom
cursors, asynchronous drivers, and Collector/DBMon testing.
