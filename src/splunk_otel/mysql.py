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

import inspect
import logging
import re
import threading
from functools import partial
from importlib import import_module

import wrapt
from opentelemetry import trace
from opentelemetry.instrumentation.utils import is_instrumentation_enabled, suppress_instrumentation
from opentelemetry.trace import INVALID_SPAN_CONTEXT, NonRecordingSpan, SpanContext, set_span_in_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_logger = logging.getLogger(__name__)
_enable_lock = threading.Lock()
_enabled = False
_CURSOR_AND_QUERY_METHOD_ARGUMENTS = 2
_QUERY_START = re.compile(r"^(SELECT|INSERT|UPDATE|DELETE|REPLACE|WITH|SHOW|EXPLAIN|DESCRIBE|DESC)\s", re.IGNORECASE)


def enable_mysql_trace_context_propagation() -> bool:
    """Enable experimental correlation for built-in Connector/Python buffered cursors."""
    global _enabled  # noqa: PLW0603 - Process-lifetime activation is serialized by _enable_lock.

    with _enable_lock:
        if _enabled:
            return True
        try:
            dbapi = import_module("opentelemetry.instrumentation.dbapi")
            connector = import_module("mysql.connector")
            cursor_types = _load_connector_cursor_types(connector)
        except ImportError:
            _logger.warning("MySQL trace context propagation requires Connector/Python and DBAPI instrumentation")
            return False

        cursor_tracer = getattr(dbapi, "CursorTracer", None)
        method = getattr(cursor_tracer, "traced_execution", None)
        try:
            parameters = tuple(inspect.signature(method).parameters)
        except (ValueError, TypeError):
            parameters = ()
        if parameters[:3] != ("self", "cursor", "query_method"):
            _logger.warning("MySQL trace context propagation requires compatible DBAPI execution methods")
            return False

        wrapper = partial(_execute_with_mysql_trace_context, connector=connector, cursor_types=cursor_types)
        wrapt.wrap_function_wrapper(cursor_tracer, "traced_execution", wrapper)
        _enabled = True
        return True


def _load_connector_cursor_types(connector):
    cursors = import_module("mysql.connector.cursor")
    cursor_types = dict.fromkeys(
        (
            cursors.MySQLCursorBuffered,
            cursors.MySQLCursorBufferedRaw,
            cursors.MySQLCursorBufferedDict,
        ),
        (connector.MySQLConnection, "have_next_result"),
    )
    if connector.HAVE_CEXT:
        cext = import_module("mysql.connector.cursor_cext")
        cursor_types.update(
            dict.fromkeys(
                (
                    cext.CMySQLCursorBuffered,
                    cext.CMySQLCursorBufferedRaw,
                    cext.CMySQLCursorBufferedDict,
                ),
                (connector.CMySQLConnection, "more_results"),
            )
        )
    return cursor_types


def _execute_with_mysql_trace_context(wrapped, cursor_tracer, args, kwargs, *, connector, cursor_types):
    if len(args) < _CURSOR_AND_QUERY_METHOD_ARGUMENTS:
        return wrapped(*args, **kwargs)
    cursor, query_method, *query_args = args
    integration = cursor_tracer._db_api_integration  # noqa: SLF001 - The DBAPI callback has no public integration accessor.
    if (
        integration.database_system != "mysql"
        or integration.connect_module is not connector
        or type(cursor) not in cursor_types
        or getattr(query_method, "__self__", None) is not cursor
        or getattr(query_method, "__func__", None) is not type(cursor).execute
    ):
        return wrapped(*args, **kwargs)

    connection_type, pending_attribute = cursor_types[type(cursor)]
    try:
        # Connector stores a weak proxy; get_self() returns the physical connection.
        connection = cursor._connection.get_self()  # noqa: SLF001 - Connector cursors have no public connection accessor.
    except (AttributeError, ReferenceError):
        return wrapped(*args, **kwargs)
    if type(connection) is not connection_type:
        return wrapped(*args, **kwargs)
    parent_context = trace.get_current_span().get_span_context()
    instrumentation_enabled = is_instrumentation_enabled()

    def _execute_query(*execution_args, **execution_kwargs):
        operation = execution_args[0] if execution_args else execution_kwargs.get("operation")
        if not _is_single_result_query(operation) or not _connection_is_ready(connection, pending_attribute):
            return query_method(*execution_args, **execution_kwargs)
        context = trace.get_current_span().get_span_context()
        if not instrumentation_enabled or context == parent_context:
            context = INVALID_SPAN_CONTEXT
        return execute_with_trace_context(connection, query_method, context, *execution_args, **execution_kwargs)

    return wrapped(cursor, _execute_query, *query_args, **kwargs)


def _is_single_result_query(operation):
    if type(operation) is not str:
        return False
    statement = operation.strip().removesuffix(";").rstrip()
    # Skip ambiguous SQL rather than parse strings, comments, or custom delimiters.
    return (
        _QUERY_START.match(statement) is not None
        and not any(token in statement for token in (";", "/*", "--", "#", "\x00"))
        and re.search(r"\bDELIMITER\b", statement, re.IGNORECASE) is None
    )


def _connection_is_ready(connection, pending_attribute):
    try:
        return connection.unread_result is False and getattr(connection, pending_attribute) is False
    except Exception:  # noqa: BLE001 - A closed connection must fail through the driver's query method.
        return False


def execute_with_trace_context(connection, query_method, span_context: SpanContext, *args, **kwargs):
    """Experimental helper for one buffered, single-result MySQL execution.

    The caller supplies the unwrapped connection and the database CLIENT span's
    context. All earlier results must be consumed. Driver hooks must enforce
    these constraints before using this helper with customer queries.
    """
    carrier = {}
    # An explicit context prevents an invalid database span from injecting a parent.
    context = set_span_in_context(NonRecordingSpan(span_context))
    TraceContextTextMapPropagator().inject(carrier, context=context)
    try:
        _set_traceparent(connection, carrier.get("traceparent"), phase="setup")
        return query_method(*args, **kwargs)
    finally:
        # Attempt cleanup even if setup failed after the server accepted its SET.
        _set_traceparent(connection, None, phase="cleanup")


def _set_traceparent(connection, value, *, phase):
    try:
        with suppress_instrumentation():
            cursor = connection.cursor()
            try:
                cursor.execute("SET @traceparent = %s", (value,))
            finally:
                cursor.close()
    except Exception as error:  # noqa: BLE001 - Internal commands must not replace the query result or error.
        _logger.warning("MySQL trace context %s failed (%s)", phase, type(error).__name__)
