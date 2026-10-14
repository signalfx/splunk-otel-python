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
from dataclasses import dataclass, field
from functools import partial
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


class _Lifetime:
    def __init__(self):
        self._active = True

    def is_active(self) -> bool:
        return self._active

    def finish(self) -> None:
        self._active = False


@dataclass(frozen=True)
class _SpanLease:
    cursor: Any
    owner: object
    traceparent: str | None
    lifetime: _Lifetime = field(default_factory=_Lifetime)


@dataclass(frozen=True)
class _QueryContext:
    connection: Any
    owner: object
    traceparent: str | None
    lifetime: _Lifetime = field(default_factory=_Lifetime)


@dataclass(frozen=True)
class _CursorAdapter:
    module: Any
    factory_name: str
    base_cursor: type
    new_internal_cursor: Callable[[Any], Any]
    asynchronous: bool = False


_span_leases: ContextVar[tuple[_SpanLease, ...]] = ContextVar("postgresql_span_leases", default=())
_active_queries: ContextVar[tuple[_QueryContext, ...]] = ContextVar("postgresql_active_queries", default=())

_enabled = False
_enable_lock = threading.Lock()
_connection_locks_lock = threading.Lock()
# Only queries using this adapter participate; raw or suppressed queries can bypass it.
_sync_connection_locks: weakref.WeakKeyDictionary[Any, threading.Lock] = weakref.WeakKeyDictionary()
_async_connection_locks: weakref.WeakKeyDictionary[Any, asyncio.Lock] = weakref.WeakKeyDictionary()


def enable_postgresql_trace_context_propagation() -> bool:
    """Enable process-lifetime PostgreSQL correlation at driver execution."""
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

        adapters = _load_cursor_adapters()
        if not adapters:
            logger.warning("PostgreSQL trace context propagation requires compatible driver cursor factories")
            return False
        for adapter in adapters:
            factory = getattr(adapter.module, adapter.factory_name, None)
            if not _has_factory_signature(factory):
                logger.warning("PostgreSQL trace context propagation requires compatible driver cursor factories")
                return False

        psycopg_adapter = next((adapter for adapter in adapters if hasattr(adapter.module, "psycopg")), None)
        if psycopg_adapter is not None and not _has_parameter_signature(
            getattr(psycopg_adapter.module.PsycopgInstrumentor, "instrument_connection", None), ("connection",)
        ):
            logger.warning("PostgreSQL trace context propagation requires compatible manual instrumentation")
            return False
        for adapter in adapters:
            wrapt.wrap_function_wrapper(adapter.module, adapter.factory_name, _cursor_factory_wrapper(adapter))
        if psycopg_adapter is not None:
            wrapt.wrap_function_wrapper(
                psycopg_adapter.module.PsycopgInstrumentor,
                "instrument_connection",
                _manual_connection_wrapper(psycopg_adapter.module),
            )

        wrapt.wrap_function_wrapper(cursor_tracer, "traced_execution", _execute_with_postgresql_trace_context)
        wrapt.wrap_function_wrapper(
            cursor_tracer,
            "traced_execution_async",
            _execute_with_postgresql_trace_context_async,
        )
        _enabled = True
        return True


def _load_cursor_adapters() -> list[_CursorAdapter]:
    adapters = []
    for name in _DRIVER_MODULE_NAMES:
        try:
            module = import_module(f"opentelemetry.instrumentation.{name}")
        except ImportError:
            continue
        if name == "psycopg":
            driver = module.psycopg
            adapters.extend(
                _CursorAdapter(
                    module=module,
                    factory_name=factory_name,
                    base_cursor=base_cursor,
                    new_internal_cursor=partial(base_cursor, row_factory=driver.rows.tuple_row),
                    asynchronous=asynchronous,
                )
                for factory_name, base_cursor, asynchronous in (
                    ("_new_cursor_factory", driver.Cursor, False),
                    ("_new_cursor_async_factory", driver.AsyncCursor, True),
                )
            )
        else:
            adapters.append(
                _CursorAdapter(
                    module=module,
                    factory_name="_new_cursor_factory",
                    base_cursor=module.psycopg2.extensions.cursor,
                    new_internal_cursor=module.psycopg2.extensions.cursor,
                )
            )
    return adapters


def _has_factory_signature(factory) -> bool:
    return _has_parameter_signature(factory, ("db_api", "base_factory"))


def _cursor_factory_wrapper(adapter: _CursorAdapter):
    mixin = _AsyncDriverCursor if adapter.asynchronous else _SyncDriverCursor
    driver_cursor = type(
        "SplunkPostgreSQLCursor",
        (mixin, adapter.base_cursor),
        {"__slots__": (), "_new_internal_cursor": staticmethod(adapter.new_internal_cursor)},
    )

    def _wrap_cursor_factory(wrapped, _instance, args, kwargs):
        base_factory = (args[1] if len(args) > 1 else kwargs.get("base_factory")) or adapter.base_cursor
        if issubclass(base_factory, mixin):
            factory = base_factory
        elif base_factory is adapter.base_cursor:
            factory = driver_cursor
        else:
            # Customer super() calls reach this class after the customer's hooks.
            factory = type("SplunkPostgreSQLCustomCursor", (base_factory, driver_cursor), {"__slots__": ()})
        if len(args) > 1:
            args = (args[0], factory, *args[2:])
        else:
            kwargs = {**kwargs, "base_factory": factory}
        return wrapped(*args, **kwargs)

    return _wrap_cursor_factory


def _manual_connection_wrapper(module):
    def _instrument_connection(wrapped, _instance, args, kwargs):
        arguments = inspect.signature(wrapped).bind(*args, **kwargs).arguments
        connection = arguments["connection"]
        original_factory = connection.cursor_factory
        result = wrapped(*args, **kwargs)
        asynchronous = isinstance(connection, module.psycopg.AsyncConnection)
        default_factory = module.psycopg.AsyncCursor if asynchronous else module.psycopg.Cursor
        if original_factory is not default_factory and connection.cursor_factory is not original_factory:
            # Upstream's manual path omits base_factory; retain the customer's hooks.
            factory = getattr(module, "_new_cursor_async_factory" if asynchronous else "_new_cursor_factory")
            options = {name: value for name, value in arguments.items() if name != "connection"}
            connection.cursor_factory = factory(base_factory=original_factory, **options)
        return result

    return _instrument_connection


class _SyncDriverCursor:
    __slots__ = ()

    def execute(self, *args, **kwargs):
        return _execute_driver(self, super().execute, args, kwargs, new_internal_cursor=self._new_internal_cursor)

    def executemany(self, *args, **kwargs):
        return _execute_driver(self, super().executemany, args, kwargs, new_internal_cursor=self._new_internal_cursor)

    def callproc(self, *args, **kwargs):
        return _execute_driver(self, super().callproc, args, kwargs, new_internal_cursor=self._new_internal_cursor)


class _AsyncDriverCursor:
    __slots__ = ()

    async def execute(self, *args, **kwargs):
        return await _execute_driver_async(
            self, super().execute, args, kwargs, new_internal_cursor=self._new_internal_cursor
        )

    async def executemany(self, *args, **kwargs):
        return await _execute_driver_async(
            self, super().executemany, args, kwargs, new_internal_cursor=self._new_internal_cursor
        )

    async def callproc(self, *args, **kwargs):
        return await _execute_driver_async(
            self, super().callproc, args, kwargs, new_internal_cursor=self._new_internal_cursor
        )


def _has_execution_signature(method: Any) -> bool:
    return _has_parameter_signature(method, ("self", "cursor", "query_method"))


def _has_parameter_signature(method: Any, names: tuple[str, ...]) -> bool:
    if not callable(method):
        return False
    try:
        parameters = tuple(inspect.signature(method).parameters.values())[: len(names)]
    except (TypeError, ValueError):
        return False
    return tuple(parameter.name for parameter in parameters) == names and all(
        parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for parameter in parameters
    )


def _execute_with_postgresql_trace_context(traced_execution, _cursor_tracer, args, kwargs):
    if not is_instrumentation_enabled() or len(args) < _CURSOR_AND_QUERY_METHOD_ARGUMENTS:
        return traced_execution(*args, **kwargs)

    cursor, query_method, *query_args = args
    if not _is_postgresql_client_cursor(cursor) or getattr(cursor.connection, "async_", False):
        return traced_execution(*args, **kwargs)

    span_context_before = trace.get_current_span().get_span_context()

    def correlated_query_method(*method_args, **method_kwargs):
        lease = _SpanLease(cursor, threading.current_thread(), _current_database_traceparent(span_context_before))
        token = _span_leases.set((*_span_leases.get(), lease))
        try:
            return query_method(*method_args, **method_kwargs)
        finally:
            lease.lifetime.finish()
            _span_leases.reset(token)

    return traced_execution(cursor, correlated_query_method, *query_args, **kwargs)


async def _execute_with_postgresql_trace_context_async(traced_execution_async, _cursor_tracer, args, kwargs):
    if not is_instrumentation_enabled() or len(args) < _CURSOR_AND_QUERY_METHOD_ARGUMENTS:
        return await traced_execution_async(*args, **kwargs)

    cursor, query_method, *query_args = args
    if not _is_postgresql_client_cursor(cursor) or getattr(cursor.connection, "async_", False):
        return await traced_execution_async(*args, **kwargs)

    span_context_before = trace.get_current_span().get_span_context()

    async def correlated_query_method(*method_args, **method_kwargs):
        lease = _SpanLease(cursor, asyncio.current_task(), _current_database_traceparent(span_context_before))
        token = _span_leases.set((*_span_leases.get(), lease))
        try:
            return await query_method(*method_args, **method_kwargs)
        finally:
            lease.lifetime.finish()
            _span_leases.reset(token)

    return await traced_execution_async(cursor, correlated_query_method, *query_args, **kwargs)


def _execute_driver(
    cursor,
    query_method: Callable[..., Any],
    args,
    kwargs,
    *,
    new_internal_cursor: Callable[[Any], Any],
):
    owner = threading.current_thread()
    lease = _live_span_lease(cursor, owner)
    if not is_instrumentation_enabled() or lease is None:
        return query_method(*args, **kwargs)
    propagate = _can_propagate_statement(cursor, query_method, args, kwargs)
    parent = _parent_query(cursor.connection, owner)
    lock = nullcontext() if parent is not None else _get_sync_connection_lock(cursor.connection)
    with lock:
        traceparent = lease.traceparent if propagate else parent.traceparent if parent is not None else None
        execution = _QueryContext(cursor.connection, owner, traceparent)
        token = _active_queries.set((*_active_queries.get(), execution))
        try:
            if propagate:
                _update_application_name(cursor.connection, traceparent, new_internal_cursor=new_internal_cursor)
            return query_method(*args, **kwargs)
        finally:
            try:
                if propagate and (traceparent is not None or parent is not None):
                    _update_application_name(
                        cursor.connection,
                        parent.traceparent if parent is not None else None,
                        new_internal_cursor=new_internal_cursor,
                    )
            finally:
                execution.lifetime.finish()
                _active_queries.reset(token)


async def _execute_driver_async(
    cursor,
    query_method: Callable[..., Any],
    args,
    kwargs,
    *,
    new_internal_cursor: Callable[[Any], Any],
):
    owner = asyncio.current_task()
    lease = _live_span_lease(cursor, owner)
    if not is_instrumentation_enabled() or lease is None:
        return await query_method(*args, **kwargs)
    propagate = _can_propagate_statement(cursor, query_method, args, kwargs)
    parent = _parent_query(cursor.connection, owner)
    lock = nullcontext() if parent is not None else _get_async_connection_lock(cursor.connection)
    async with lock:
        traceparent = lease.traceparent if propagate else parent.traceparent if parent is not None else None
        execution = _QueryContext(cursor.connection, owner, traceparent)
        token = _active_queries.set((*_active_queries.get(), execution))
        try:
            if propagate:
                await _update_application_name_async(
                    cursor.connection, traceparent, new_internal_cursor=new_internal_cursor
                )
            return await query_method(*args, **kwargs)
        finally:
            try:
                if propagate and (traceparent is not None or parent is not None):
                    await _update_application_name_async(
                        cursor.connection,
                        parent.traceparent if parent is not None else None,
                        new_internal_cursor=new_internal_cursor,
                    )
            finally:
                execution.lifetime.finish()
                _active_queries.reset(token)


def _live_span_lease(cursor, owner: object) -> _SpanLease | None:
    return next(
        (
            lease
            for lease in reversed(_span_leases.get())
            if lease.cursor is cursor and lease.owner is owner and lease.lifetime.is_active()
        ),
        None,
    )


def _parent_query(connection, owner: object) -> _QueryContext | None:
    # Context copies outlive their calls; neither copied nor expired ownership grants the lock.
    return next(
        (
            query
            for query in reversed(_active_queries.get())
            if query.connection is connection and query.owner is owner and query.lifetime.is_active()
        ),
        None,
    )


def _can_propagate_statement(cursor, query_method, args, kwargs) -> bool:
    if query_method.__name__ == "callproc":
        return True
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
    if statement.startswith("("):
        return True
    operation = re.match(r"[a-z_][a-z_0-9$]*", statement, re.IGNORECASE)
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


def _update_application_name(connection, traceparent: str | None, *, new_internal_cursor: Callable[[Any], Any]) -> None:
    statement = _application_name_statement(traceparent)
    try:
        cursor = new_internal_cursor(connection)
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


async def _update_application_name_async(
    connection, traceparent: str | None, *, new_internal_cursor: Callable[[Any], Any]
) -> None:
    statement = _application_name_statement(traceparent)
    try:
        cursor = new_internal_cursor(connection)
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
