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

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import threading
import weakref
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

import wrapt
from opentelemetry import trace
from opentelemetry.instrumentation.utils import is_instrumentation_enabled, suppress_instrumentation

if TYPE_CHECKING:
    from collections.abc import Callable

    from opentelemetry.trace import SpanContext

logger = logging.getLogger(__name__)

_SET_APPLICATION_NAME_DEFAULT = "SET application_name = DEFAULT"
_DRIVER_MODULE_NAMES = ("psycopg", "psycopg2")
_CURSOR_AND_QUERY_METHOD_ARGUMENTS = 2
_TRANSACTION_OPERATIONS = frozenset(
    {"BEGIN", "START", "COMMIT", "END", "ROLLBACK", "ABORT", "SAVEPOINT", "RELEASE", "PREPARE", "CALL", "DO"}
)


@dataclass(frozen=True)
class _QueryContext:
    connection: Any
    owner: object
    traceparent: str | None


_active_queries: ContextVar[tuple[_QueryContext, ...]] = ContextVar("postgresql_active_queries", default=())

_enabled = False
_enable_lock = threading.Lock()
_connection_locks_lock = threading.Lock()
# Only queries using this adapter participate; raw or suppressed queries can bypass it.
_sync_connection_locks: weakref.WeakKeyDictionary[Any, threading.Lock] = weakref.WeakKeyDictionary()
_async_connection_locks: weakref.WeakKeyDictionary[Any, asyncio.Lock] = weakref.WeakKeyDictionary()


def enable_postgresql_trace_context_propagation() -> bool:
    """Enable process-lifetime PostgreSQL correlation for installed DBAPI instrumentation."""
    global _enabled  # noqa: PLW0603

    with _enable_lock:
        if _enabled:
            return True

        try:
            dbapi = import_module("opentelemetry.instrumentation.dbapi")
        except ImportError:
            logger.warning("PostgreSQL trace context propagation requires DBAPI instrumentation")
            return False

        cursor_tracer = getattr(dbapi, "CursorTracer", None)
        for name in ("traced_execution", "traced_execution_async"):
            method = getattr(cursor_tracer, name, None)
            if not _has_execution_signature(method):
                logger.warning("PostgreSQL trace context propagation requires compatible DBAPI execution methods")
                return False

        wrapt.wrap_function_wrapper(cursor_tracer, "traced_execution", _execute_with_postgresql_trace_context)
        wrapt.wrap_function_wrapper(
            cursor_tracer,
            "traced_execution_async",
            _execute_with_postgresql_trace_context_async,
        )
        _enabled = True
        return True


def _has_execution_signature(method: Any) -> bool:
    if not callable(method):
        return False
    try:
        parameters = tuple(inspect.signature(method).parameters.values())[:3]
    except (TypeError, ValueError):
        return False
    return tuple(parameter.name for parameter in parameters) == ("self", "cursor", "query_method") and all(
        parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for parameter in parameters
    )


def _execute_with_postgresql_trace_context(traced_execution, _cursor_tracer, args, kwargs):
    if not is_instrumentation_enabled() or len(args) < _CURSOR_AND_QUERY_METHOD_ARGUMENTS:
        return traced_execution(*args, **kwargs)

    cursor, query_method, *query_args = args
    if not _is_postgresql_client_cursor(cursor) or getattr(cursor.connection, "async_", False):
        return traced_execution(*args, **kwargs)

    propagate = _can_propagate_statement(cursor, query_args, kwargs)
    span_context_before = trace.get_current_span().get_span_context()

    def correlated_query_method(*method_args, **method_kwargs):
        return _execute_correlated(
            cursor,
            query_method,
            span_context_before,
            method_args,
            method_kwargs,
            propagate=propagate,
        )

    return traced_execution(cursor, correlated_query_method, *query_args, **kwargs)


async def _execute_with_postgresql_trace_context_async(traced_execution_async, _cursor_tracer, args, kwargs):
    if not is_instrumentation_enabled() or len(args) < _CURSOR_AND_QUERY_METHOD_ARGUMENTS:
        return await traced_execution_async(*args, **kwargs)

    cursor, query_method, *query_args = args
    if not _is_postgresql_client_cursor(cursor) or getattr(cursor.connection, "async_", False):
        return await traced_execution_async(*args, **kwargs)

    propagate = _can_propagate_statement(cursor, query_args, kwargs)
    span_context_before = trace.get_current_span().get_span_context()

    async def correlated_query_method(*method_args, **method_kwargs):
        return await _execute_correlated_async(
            cursor,
            query_method,
            span_context_before,
            method_args,
            method_kwargs,
            propagate=propagate,
        )

    return await traced_execution_async(cursor, correlated_query_method, *query_args, **kwargs)


def _execute_correlated(
    cursor,
    query_method: Callable[..., Any],
    span_context_before: SpanContext,
    args,
    kwargs,
    *,
    propagate: bool,
):
    owner = threading.current_thread()
    parent = _parent_query(cursor.connection, owner)
    lock = nullcontext() if parent is not None else _get_sync_connection_lock(cursor.connection)
    with lock:
        traceparent = _current_database_traceparent(span_context_before) if propagate else None
        token = _active_queries.set((*_active_queries.get(), _QueryContext(cursor.connection, owner, traceparent)))
        try:
            if propagate:
                _update_application_name(cursor.connection, traceparent)
            return query_method(*args, **kwargs)
        finally:
            try:
                if propagate and (traceparent is not None or parent is not None):
                    _update_application_name(cursor.connection, parent.traceparent if parent is not None else None)
            finally:
                _active_queries.reset(token)


async def _execute_correlated_async(
    cursor,
    query_method: Callable[..., Any],
    span_context_before: SpanContext,
    args,
    kwargs,
    *,
    propagate: bool,
):
    owner = asyncio.current_task()
    parent = _parent_query(cursor.connection, owner)
    lock = nullcontext() if parent is not None else _get_async_connection_lock(cursor.connection)
    async with lock:
        traceparent = _current_database_traceparent(span_context_before) if propagate else None
        token = _active_queries.set((*_active_queries.get(), _QueryContext(cursor.connection, owner, traceparent)))
        try:
            if propagate:
                await _update_application_name_async(cursor.connection, traceparent)
            return await query_method(*args, **kwargs)
        finally:
            try:
                if propagate and (traceparent is not None or parent is not None):
                    await _update_application_name_async(
                        cursor.connection, parent.traceparent if parent is not None else None
                    )
            finally:
                _active_queries.reset(token)


def _parent_query(connection, owner: object) -> _QueryContext | None:
    # Context can be copied into another thread/task; that caller must acquire the lock.
    return next(
        (query for query in reversed(_active_queries.get()) if query.connection is connection and query.owner is owner),
        None,
    )


def _can_propagate_statement(cursor, args, kwargs) -> bool:
    statement = args[0] if args else kwargs.get("query")
    if isinstance(statement, bytes):
        statement = statement.decode("ascii", errors="replace")
    elif any(base.__module__ in ("psycopg.sql", "psycopg2.sql") for base in type(statement).__mro__):
        statement = statement.as_string(cursor.connection)
    if not isinstance(statement, str):
        return False

    # SET and reset cannot safely straddle SQL transaction boundaries. Avoid
    # batches too: even a SELECT-first batch can commit or begin a transaction.
    statement = statement.strip().removesuffix(";")
    if ";" in statement:
        return False
    statement = _strip_leading_comments(statement)
    operation = re.match(r"[a-z]+", statement, re.IGNORECASE)
    return operation is not None and operation[0].upper() not in _TRANSACTION_OPERATIONS


def _strip_leading_comments(statement: str) -> str:
    statement = statement.lstrip()
    while statement.startswith(("--", "/*")):
        if statement.startswith("--"):
            _, _, statement = statement.partition("\n")
        else:
            depth = 0
            for delimiter in re.finditer(r"/\*|\*/", statement):
                depth += 1 if delimiter[0] == "/*" else -1
                if depth == 0:
                    statement = statement[delimiter.end() :]
                    break
            else:
                return ""
        statement = statement.lstrip()
    return statement


def _get_sync_connection_lock(connection) -> threading.Lock:
    with _connection_locks_lock:
        lock = _sync_connection_locks.get(connection)
        if lock is None:
            lock = threading.Lock()
            _sync_connection_locks[connection] = lock
        return lock


def _get_async_connection_lock(connection) -> asyncio.Lock:
    with _connection_locks_lock:
        lock = _async_connection_locks.get(connection)
        if lock is None:
            lock = asyncio.Lock()
            _async_connection_locks[connection] = lock
        return lock


def _current_database_traceparent(span_context_before: SpanContext) -> str | None:
    current = trace.get_current_span().get_span_context()
    if not current.is_valid or current == span_context_before:
        return None
    return f"00-{current.trace_id:032x}-{current.span_id:016x}-{int(current.trace_flags) & 0xFF:02x}"


def _update_application_name(connection, traceparent: str | None) -> None:
    statement = _application_name_statement(traceparent)
    try:
        cursor = connection.cursor()
        try:
            with suppress_instrumentation():
                result = cursor.execute(statement)
            if inspect.iscoroutine(result):
                result.close()
            if inspect.isawaitable(result):
                logger.error("Synchronous PostgreSQL cursor returned an awaitable")
        finally:
            cursor.close()
    except Exception:
        logger.exception("Failed to set PostgreSQL application_name")


async def _update_application_name_async(connection, traceparent: str | None) -> None:
    statement = _application_name_statement(traceparent)
    try:
        cursor = connection.cursor()
        try:
            with suppress_instrumentation():
                result = cursor.execute(statement)
                if inspect.isawaitable(result):
                    await result
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
    except Exception:
        logger.exception("Failed to set PostgreSQL application_name")


def _application_name_statement(traceparent: str | None) -> str:
    if traceparent is None:
        return _SET_APPLICATION_NAME_DEFAULT
    return f"SET application_name = '{traceparent}'"


def _is_postgresql_client_cursor(cursor) -> bool:
    # Named cursors execute SQL during later fetches, outside this query's span.
    if getattr(cursor, "name", None):
        return False
    return any(_is_postgresql_module(cursor_class.__module__) for cursor_class in type(cursor).__mro__)


def _is_postgresql_module(module_name: str) -> bool:
    return any(module_name == name or module_name.startswith(f"{name}.") for name in _DRIVER_MODULE_NAMES)
