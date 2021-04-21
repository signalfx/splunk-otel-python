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

import unittest

from opentelemetry import trace
from opentelemetry.instrumentation.propagators import get_global_response_propagator
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.b3 import B3Format

from splunk_otel.options import Options
from splunk_otel.propagators import ServerTimingResponsePropagator
from splunk_otel.tracing import _configure_tracing


class TestPropagator(unittest.TestCase):
    def test_sets_b3_is_global_propagator(self):
        _configure_tracing(Options())
        propagtor = get_global_textmap()
        self.assertIsInstance(propagtor, B3Format)

    def test_server_timing_is_global_response_propagator(self):
        _configure_tracing(Options())
        propagtor = get_global_response_propagator()
        self.assertIsInstance(propagtor, ServerTimingResponsePropagator)


class TestServerTimingResponsePropagator(unittest.TestCase):
    def test_inject(self):
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
        self.assertEqual(carrier["Access-Control-Expose-Headers"], "Server-Timing")
        self.assertEqual(
            carrier["Server-Timing"],
            'traceparent;desc="00-00000000000000000000000000000001-0000000000000002-01"',
        )

    def test_inject_not_sampled(self):
        span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=1,
                span_id=2,
                is_remote=False,
                trace_flags=trace.TraceFlags(0),
                trace_state=trace.DEFAULT_TRACE_STATE,
            ),
        )

        ctx = trace.set_span_in_context(span)
        prop = ServerTimingResponsePropagator()
        carrier = {}
        prop.inject(carrier, ctx)
        self.assertEqual(carrier["Access-Control-Expose-Headers"], "Server-Timing")
        self.assertEqual(
            carrier["Server-Timing"],
            'traceparent;desc="00-00000000000000000000000000000001-0000000000000002-00"',
        )
