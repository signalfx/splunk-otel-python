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

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import baggage, trace
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, TracerProvider
from opentelemetry.trace import SpanContext

from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor, _should_process_context


def _processor():
    return CallgraphsSpanProcessor(Resource({}), MagicMock())


class TestShouldProcessContext:
    def test_returns_true_when_no_parent_span(self):
        assert _should_process_context(Context()) is True

    def test_returns_true_when_parent_is_remote(self):
        span = trace.NonRecordingSpan(
            SpanContext(
                trace_id=1,
                span_id=2,
                is_remote=True,
            ),
        )
        ctx = trace.set_span_in_context(span, Context())
        assert _should_process_context(ctx) is True

    def test_returns_false_when_parent_is_local(self):
        span = trace.NonRecordingSpan(
            SpanContext(
                trace_id=1,
                span_id=2,
                is_remote=False,
            ),
        )
        ctx = trace.set_span_in_context(span, Context())
        assert _should_process_context(ctx) is False


class TestCallgraphsSpanProcessor:
    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_start_does_nothing_when_baggage_is_none(self, mock_profiling_context):
        processor = _processor()
        span = MagicMock(spec=Span)

        processor.on_start(span, Context())

        span.set_attribute.assert_not_called()
        mock_profiling_context.return_value.start.assert_not_called()

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_start_does_nothing_when_baggage_is_off(self, mock_profiling_context):
        processor = _processor()
        span = MagicMock(spec=Span)
        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "off", Context())

        processor.on_start(span, ctx)

        span.set_attribute.assert_not_called()
        mock_profiling_context.return_value.start.assert_not_called()

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_start_does_nothing_when_parent_is_local(self, mock_profiling_context):
        processor = _processor()
        span = MagicMock(spec=Span)

        parent_span = trace.NonRecordingSpan(
            SpanContext(trace_id=1, span_id=2, is_remote=False),
        )
        ctx = trace.set_span_in_context(parent_span, Context())
        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", ctx)

        processor.on_start(span, ctx)

        span.set_attribute.assert_not_called()
        mock_profiling_context.return_value.start.assert_not_called()

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_start_activates_profiling_when_baggage_is_highest(self, mock_profiling_context):
        processor = _processor()

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

        processor.on_start(span, ctx)

        span.set_attribute.assert_called_once_with("splunk.snapshot.profiling", True)
        mock_profiling_context.return_value.start.assert_called_once()
        assert 456 in processor._span_id_to_trace_id  # noqa SLF001
        assert processor._span_id_to_trace_id[456] == 123  # noqa SLF001

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_end_removes_span_from_tracking(self, mock_profiling_context):
        processor = _processor()
        processor._span_id_to_trace_id[456] = 123  # noqa SLF001

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        processor.on_end(span)

        assert 456 not in processor._span_id_to_trace_id  # noqa SLF001

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_end_pauses_profiler_when_no_active_spans(self, mock_profiling_context):
        processor = _processor()
        processor._span_id_to_trace_id[456] = 123  # noqa SLF001

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        processor.on_end(span)

        mock_profiling_context.return_value.pause_after.assert_called_once_with(60.0)

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_end_does_not_pause_profiler_when_other_spans_active(self, mock_profiling_context):
        processor = _processor()
        processor._span_id_to_trace_id[456] = 123  # noqa SLF001
        processor._span_id_to_trace_id[789] = 123  # noqa SLF001

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        processor.on_end(span)

        mock_profiling_context.return_value.pause_after.assert_not_called()

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_end_ignores_untracked_spans(self, mock_profiling_context):
        processor = _processor()

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        processor.on_end(span)

        mock_profiling_context.return_value.pause_after.assert_not_called()

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_filter_stacktraces_keeps_active_traces(self, mock_profiling_context):
        processor = _processor()
        processor._span_id_to_trace_id[456] = 123  # noqa SLF001

        stacktraces = [
            {"tid": 1, "frames": []},
            {"tid": 2, "frames": []},
            {"tid": 3, "frames": []},
        ]
        active_trace_contexts = {
            1: (123, 456),
            2: (999, 888),
        }

        result = processor._filter_stacktraces(stacktraces, active_trace_contexts)  # noqa SLF001

        assert len(result) == 1
        assert result[0]["tid"] == 1

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_filter_stacktraces_returns_empty_when_no_active_traces(self, mock_profiling_context):
        processor = _processor()

        stacktraces = [
            {"tid": 1, "frames": []},
            {"tid": 2, "frames": []},
        ]
        active_trace_contexts = {
            1: (123, 456),
            2: (999, 888),
        }

        result = processor._filter_stacktraces(stacktraces, active_trace_contexts)  # noqa SLF001

        assert len(result) == 0


@patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
def test_shutdown_prevents_sampling_for_later_spans(mock_profiling_context):
    processor = _processor()
    span = MagicMock(spec=Span)
    context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

    processor.shutdown()
    processor.on_start(span, context)

    mock_profiling_context.return_value.stop.assert_called_once_with()
    mock_profiling_context.return_value.start.assert_not_called()
    span.set_attribute.assert_not_called()


@pytest.mark.parametrize("failure", ["start", "pause"])
def test_snapshot_sampling_failure_does_not_escape_span_callbacks(profiling_timer_type, failure):
    logger = NoOpLoggerProvider().get_logger("test")
    processor = CallgraphsSpanProcessor(Resource({}), logger)
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("test")
    context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
    (timer,) = profiling_timer_type.instances
    timer.fail_start = failure == "start"
    timer.fail_pause = failure == "pause"

    try:
        span = tracer.start_span("first request", context=context)
        span.end()
        assert timer.pause_count == (1 if failure == "pause" else 0)

        timer.fail_start = False
        timer.fail_pause = False
        span = tracer.start_span("next request", context=context)
        span.end()
        assert timer.pause_count == (2 if failure == "pause" else 1)
    finally:
        timer.fail_start = False
        timer.fail_pause = False
        provider.shutdown()


def test_failed_snapshot_stop_does_not_notify_shutdown(profiling_timer_type):
    stopped = []
    processor = CallgraphsSpanProcessor(
        Resource({}), NoOpLoggerProvider().get_logger("test"), on_shutdown=stopped.append
    )
    (timer,) = profiling_timer_type.instances
    timer.fail_stop = True

    processor.shutdown()
    assert stopped == []

    timer.fail_stop = False
    processor.shutdown()
    assert stopped == [processor]


@pytest.mark.usefixtures("profiling_timer_type")
def test_snapshot_shutdown_callback_failure_does_not_escape(caplog):
    def _fake_shutdown_callback(_processor):
        message = "shutdown callback failed"
        raise RuntimeError(message)

    processor = CallgraphsSpanProcessor(
        Resource({}), NoOpLoggerProvider().get_logger("test"), on_shutdown=_fake_shutdown_callback
    )

    processor.shutdown()

    assert "Snapshot profiler shutdown callback failed" in caplog.text


@pytest.mark.parametrize("callback", ["on_start", "on_end"])
@pytest.mark.usefixtures("profiling_timer_type")
def test_snapshot_callback_contains_span_failures(callback, caplog):
    class FakeSpan:
        def set_attribute(self, _name, _value):
            message = "span failed"
            raise RuntimeError(message)

        def get_span_context(self):
            message = "span failed"
            raise RuntimeError(message)

    processor = CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test"))

    if callback == "on_start":
        context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
        processor.on_start(FakeSpan(), context)
    else:
        processor.on_end(FakeSpan())

    assert "span failed" in caplog.text
