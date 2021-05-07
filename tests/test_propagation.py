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

import os
from importlib import reload
from unittest import TestCase, mock

from opentelemetry import propagate, trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.instrumentation.propagators import get_global_response_propagator
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from splunk_otel.options import Options
from splunk_otel.propagators import ServerTimingResponsePropagator
from splunk_otel.tracing import _configure_tracing


class TestPropagator(TestCase):
    def test_sets_tracecontext_and_baggage_are_default_propagator(self):
        reload(propagate)
        _configure_tracing(Options())
        propagator = get_global_textmap()
        self.assertIsInstance(propagator, CompositePropagator)
        propagators = propagator._propagators  # pylint: disable=protected-access
        self.assertEqual(len(propagators), 2)
        self.assertIsInstance(propagators[0], TraceContextTextMapPropagator)
        self.assertIsInstance(propagators[1], W3CBaggagePropagator)

    @mock.patch.dict(
        os.environ,
        {"OTEL_PROPAGATORS": "baggage"},
    )
    def test_set_custom_propagator(self):
        reload(propagate)
        _configure_tracing(Options())
        propagator = get_global_textmap()
        self.assertIsInstance(propagator, CompositePropagator)
        propagators = propagator._propagators  # pylint: disable=protected-access
        self.assertEqual(len(propagators), 1)
        self.assertIsInstance(propagators[0], W3CBaggagePropagator)

    def test_server_timing_is_default_response_propagator(self):
        _configure_tracing(Options())
        propagtor = get_global_response_propagator()
        self.assertIsInstance(propagtor, ServerTimingResponsePropagator)

    def test_server_timing_is_global_response_propagator_disabled_code(self):
        _configure_tracing(Options(trace_response_header_enabled=False))
        self.assertIsNone(get_global_response_propagator())

    @mock.patch.dict(
        os.environ,
        {"SPLUNK_TRACE_RESPONSE_HEADER_ENABLED": "false"},
    )
    def test_server_timing_is_global_response_propagator_disabled_env(self):
        _configure_tracing(Options())
        self.assertIsNone(get_global_response_propagator())


class TestServerTimingResponsePropagator(TestCase):
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
