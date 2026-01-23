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

import typing
import random

from opentelemetry import baggage, trace
from opentelemetry.context.context import Context
from opentelemetry.instrumentation.propagators import (
    _HTTP_HEADER_ACCESS_CONTROL_EXPOSE_HEADERS,
    ResponsePropagator,
    default_setter,
)
from opentelemetry.propagators import textmap
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, Decision
from opentelemetry.trace import format_span_id, format_trace_id

_SPLUNK_TRACE_SNAPSHOT_VOLUME = "splunk.trace.snapshot.volume"


class ServerTimingResponsePropagator(ResponsePropagator):
    def inject(
        self,
        carrier: textmap.CarrierT,
        context: typing.Optional[Context] = None,
        setter: textmap.Setter = default_setter,  # type: ignore
    ) -> None:
        """
        Injects SpanContext into the HTTP response carrier.

        e.g.:
        Server-Timing: traceparent;desc="00-e899d68fca52b66d3facae0bdaf764db-159efb97d6b56568-01"
        Access-Control-Expose-Headers: Server-Timing
        """
        span = trace.get_current_span(context)
        span_context = span.get_span_context()
        if span_context == trace.INVALID_SPAN_CONTEXT:
            return

        header_name = "Server-Timing"
        trace_id = format_trace_id(span_context.trace_id)
        span_id = format_span_id(span_context.span_id)

        setter.set(
            carrier,
            header_name,
            f'traceparent;desc="00-{trace_id}-{span_id}-01"',
        )
        setter.set(
            carrier,
            _HTTP_HEADER_ACCESS_CONTROL_EXPOSE_HEADERS,
            header_name,
        )


def _with_volume_baggage(is_selected: bool, context: typing.Optional[Context]) -> Context:  # noqa FBT001
    baggage_value = "highest" if is_selected else "off"
    return baggage.set_baggage(_SPLUNK_TRACE_SNAPSHOT_VOLUME, baggage_value, context)


class CallgraphsPropagator(textmap.TextMapPropagator):
    selection_probability: float

    def __init__(self, selection_probability: float = 0.01):
        self.selection_probability = selection_probability
        self.sampler = TraceIdRatioBased(selection_probability)

    def extract(self, carrier, context, getter):
        volume_baggage = baggage.get_baggage(_SPLUNK_TRACE_SNAPSHOT_VOLUME, context)

        if volume_baggage is None:
            return self._attach_volume_baggage(context)

        if volume_baggage in {"highest", "off"}:
            return context

        return self._attach_volume_baggage(context)

    def inject(self, carrier, context, setter):
        pass

    def fields(self) -> set[str]:
        return set()

    def _attach_volume_baggage(self, context: typing.Optional[Context]) -> Context:
        span = trace.get_current_span(context)

        if not span.get_span_context().is_valid:
            is_selected = random.random() < self.selection_probability  # noqa S311
            return _with_volume_baggage(is_selected, context)

        is_selected = (
            self.sampler.should_sample(context, span.get_span_context().trace_id, "splunk.snapshot.profiling").decision
            == Decision.RECORD_AND_SAMPLE
        )

        return _with_volume_baggage(is_selected, context)
