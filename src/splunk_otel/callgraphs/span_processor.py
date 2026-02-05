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

from typing import Optional

from opentelemetry import baggage, trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

from splunk_otel.profile import ProfilingContext


def _should_process_context(context: Optional[Context]) -> bool:
    parent_span = trace.get_current_span(context).get_span_context()

    if not parent_span.is_valid:
        return True

    return parent_span.is_remote


class CallgraphsSpanProcessor(SpanProcessor):
    def __init__(self, service_name: str, sampling_interval: Optional[int] = 10):
        self.span_id_to_trace_id: dict[int, int] = {}
        self.profiler = ProfilingContext(
            service_name, sampling_interval, self._filter_stacktraces, instrumentation_source="snapshot"
        )

    def on_start(self, span: Span, parent_context: Optional[Context] = None) -> None:
        if not _should_process_context(parent_context):
            return

        ctx_baggage = baggage.get_baggage("splunk.trace.snapshot.volume", parent_context)

        if ctx_baggage is None:
            return

        if ctx_baggage == "highest":
            span.set_attribute("splunk.snapshot.profiling", True)

            span_ctx = span.get_span_context()

            if span_ctx is None:
                return

            self.span_id_to_trace_id[span_ctx.span_id] = span_ctx.trace_id
            self.profiler.start()

    def on_end(self, span: ReadableSpan) -> None:
        span_id = span.get_span_context().span_id
        trace_id = self.span_id_to_trace_id.get(span_id)

        if trace_id is None:
            return

        del self.span_id_to_trace_id[span_id]

        if len(self.span_id_to_trace_id) == 0:
            self.profiler.pause_after(60.0)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def _filter_stacktraces(self, stacktraces, active_trace_contexts):
        filtered = []

        for stacktrace in stacktraces:
            thread_id = stacktrace["tid"]

            maybe_context = active_trace_contexts.get(thread_id)

            if maybe_context is not None:
                (trace_id, _span_id) = maybe_context
                if trace_id in self.span_id_to_trace_id.values():
                    filtered.append(stacktrace)

        return filtered
