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

from opentelemetry import baggage, trace
from opentelemetry.context import Context
from splunk_otel.propagator import CallgraphsPropagator, ServerTimingResponsePropagator


def test_inject():
    span = trace.NonRecordingSpan(
        trace.SpanContext(
            trace_id=1,
            span_id=2,
            is_remote=False,
            trace_flags=trace.TraceFlags(1),
            trace_state=trace.DEFAULT_TRACE_STATE,
        ),
    )

    ctx = trace.set_span_in_context(span)
    prop = ServerTimingResponsePropagator()
    carrier = {}
    prop.inject(carrier, ctx)
    assert carrier["Access-Control-Expose-Headers"] == "Server-Timing"
    assert carrier["Server-Timing"] == 'traceparent;desc="00-00000000000000000000000000000001-0000000000000002-01"'


class TestCallgraphsPropagator:
    def test_extract_sets_highest_when_trace_is_selected(self):
        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=1,
                span_id=2,
                is_remote=False,
            ),
        )
        ctx = trace.set_span_in_context(span, Context())

        prop = CallgraphsPropagator(selection_probability=1.0)
        result_ctx = prop.extract({}, ctx, None)

        volume = baggage.get_baggage("splunk.trace.snapshot.volume", result_ctx)
        assert volume == "highest"

    def test_extract_sets_off_when_not_trace_is_not_selected(self):
        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=1,
                span_id=2,
                is_remote=False,
            ),
        )
        ctx = trace.set_span_in_context(span, Context())

        prop = CallgraphsPropagator(selection_probability=0.0)
        result_ctx = prop.extract({}, ctx, None)

        volume = baggage.get_baggage("splunk.trace.snapshot.volume", result_ctx)
        assert volume == "off"

    def test_extract_preserves_existing_highest_baggage(self):
        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

        prop = CallgraphsPropagator(selection_probability=0.0)
        result_ctx = prop.extract({}, ctx, None)

        volume = baggage.get_baggage("splunk.trace.snapshot.volume", result_ctx)
        assert volume == "highest"

    def test_extract_preserves_existing_off_baggage(self):
        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "off", Context())

        prop = CallgraphsPropagator(selection_probability=1.0)
        result_ctx = prop.extract({}, ctx, None)

        volume = baggage.get_baggage("splunk.trace.snapshot.volume", result_ctx)
        assert volume == "off"

    def test_extract_resets_invalid_baggage_value(self):
        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "invalid", Context())
        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=1,
                span_id=2,
                is_remote=False,
            ),
        )
        ctx = trace.set_span_in_context(span, ctx)

        prop = CallgraphsPropagator(selection_probability=1.0)
        result_ctx = prop.extract({}, ctx, None)

        volume = baggage.get_baggage("splunk.trace.snapshot.volume", result_ctx)
        assert volume == "highest"

    def test_sampling_is_consistent_for_same_trace_id(self):
        trace_id = 12345678901234567890

        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=trace_id,
                span_id=1,
                is_remote=False,
            ),
        )
        ctx = trace.set_span_in_context(span, Context())

        prop = CallgraphsPropagator(selection_probability=0.5)

        results = []
        for _ in range(16):
            result_ctx = prop.extract({}, ctx, None)
            volume = baggage.get_baggage("splunk.trace.snapshot.volume", result_ctx)
            results.append(volume)

        assert all(r == results[0] for r in results)
