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
import logging
import os
import threading
import weakref
from functools import partial
from typing import TYPE_CHECKING, cast

from opentelemetry import baggage, trace
from opentelemetry._logs import Logger
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

from splunk_otel._logging import log_exception
from splunk_otel.profile import ProfilingContext
from splunk_otel.propagator import _SPLUNK_TRACE_SNAPSHOT_VOLUME

if TYPE_CHECKING:
    from opentelemetry.trace import SpanContext

_DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS = 10
_logger = logging.getLogger(__name__)


def _should_process_context(context: Context | None) -> bool:
    parent_span = trace.get_current_span(context).get_span_context()

    is_root_span = not parent_span.is_valid

    return is_root_span or parent_span.is_remote


class CallgraphsSpanProcessor(SpanProcessor):
    def __init__(
        self,
        resource: Resource,
        logger: Logger,
        sampling_interval: int = _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS,
    ):
        self._span_id_to_trace_id: dict[int, int] = {}
        self._lock = threading.Lock()
        self._shutdown = False
        self._new_profiler = partial(
            ProfilingContext,
            resource,
            sampling_interval,
            logger,
            self._filter_stacktraces,
            instrumentation_source="snapshot",
        )
        self._profiler = self._new_profiler()
        if hasattr(os, "register_at_fork"):
            after_fork_ref = weakref.WeakMethod(self._after_fork)

            def reset_snapshot_after_fork():
                after_fork = after_fork_ref()
                if after_fork is not None:
                    after_fork()

            os.register_at_fork(after_in_child=reset_snapshot_after_fork)

    def _after_fork(self) -> None:
        if self._shutdown:
            return
        try:
            # Parent threads can hold either lock when fork() copies the processor.
            self._lock = threading.Lock()
            self._span_id_to_trace_id = {}
            self._profiler = self._new_profiler()
        except Exception:  # noqa: BLE001
            log_exception(_logger, "Failed to reset snapshot profiling after fork")

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        try:
            if self._profiler.is_current_process():
                self._start_snapshot_for_span(span, parent_context)
        except Exception:  # noqa: BLE001
            log_exception(_logger, "Failed to handle snapshot span start")

    def _start_snapshot_for_span(self, span: Span, parent_context: Context | None = None) -> None:
        if not _should_process_context(parent_context):
            return

        ctx_baggage = baggage.get_baggage(_SPLUNK_TRACE_SNAPSHOT_VOLUME, parent_context)

        if ctx_baggage is None:
            return

        if ctx_baggage == "highest":
            span_ctx = span.get_span_context()

            if span_ctx is None:
                return

            with self._lock:
                self._span_id_to_trace_id[span_ctx.span_id] = span_ctx.trace_id
            if not self._profiler.start():
                with self._lock:
                    self._span_id_to_trace_id.pop(span_ctx.span_id, None)
                return
            span.set_attribute("splunk.snapshot.profiling", True)

    def on_end(self, span: ReadableSpan) -> None:
        try:
            if self._profiler.is_current_process():
                self._pause_snapshot_after_span(span)
        except Exception:  # noqa: BLE001
            log_exception(_logger, "Failed to handle snapshot span end")

    def _pause_snapshot_after_span(self, span: ReadableSpan) -> None:
        span_id = cast("SpanContext", span.get_span_context()).span_id
        trace_id = self._span_id_to_trace_id.get(span_id)

        if trace_id is None:
            return

        with self._lock:
            self._span_id_to_trace_id.pop(span_id, None)

            if len(self._span_id_to_trace_id) == 0:
                self._profiler.pause_after(60.0)

    def shutdown(self) -> None:
        self._shutdown = True
        self._profiler.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def _filter_stacktraces(self, stacktraces, active_trace_contexts):
        if not self._profiler.is_current_process():
            return []
        filtered = []
        with self._lock:
            trace_ids = set(self._span_id_to_trace_id.values())

        for stacktrace in stacktraces:
            thread_id = stacktrace["tid"]

            maybe_context = active_trace_contexts.get(thread_id)

            if maybe_context is not None:
                (trace_id, _span_id) = maybe_context
                if trace_id in trace_ids:
                    filtered.append(stacktrace)

        return filtered
