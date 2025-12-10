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

from opentelemetry import trace
from splunk_otel.propagator import ServerTimingResponsePropagator


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
