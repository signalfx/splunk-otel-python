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

import base64
import gzip
import logging
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
from threading import Event, Thread
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import baggage, trace
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, TracerProvider
from opentelemetry.trace import SpanContext

from splunk_otel import profile_pb2
from splunk_otel.callgraphs import CallgraphsSpanProcessor
from splunk_otel.callgraphs.span_processor import _should_process_context


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
        mock_profiling_context.return_value._start.assert_not_called()  # noqa: SLF001

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_start_does_nothing_when_baggage_is_off(self, mock_profiling_context):
        processor = _processor()
        span = MagicMock(spec=Span)
        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "off", Context())

        processor.on_start(span, ctx)

        span.set_attribute.assert_not_called()
        mock_profiling_context.return_value._start.assert_not_called()  # noqa: SLF001

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
        mock_profiling_context.return_value._start.assert_not_called()  # noqa: SLF001

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_start_activates_profiling_when_baggage_is_highest(self, mock_profiling_context):
        processor = _processor()

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        ctx = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

        processor.on_start(span, ctx)

        span.set_attribute.assert_called_once_with("splunk.snapshot.profiling", True)
        mock_profiling_context.return_value._start.assert_called_once()  # noqa: SLF001
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

        mock_profiling_context.return_value._pause_after.assert_called_once_with(60.0)  # noqa: SLF001

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_end_does_not_pause_profiler_when_other_spans_active(self, mock_profiling_context):
        processor = _processor()
        processor._span_id_to_trace_id[456] = 123  # noqa SLF001
        processor._span_id_to_trace_id[789] = 123  # noqa SLF001

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        processor.on_end(span)

        mock_profiling_context.return_value._pause_after.assert_not_called()  # noqa: SLF001

    @patch("splunk_otel.callgraphs.span_processor.ProfilingContext")
    def test_on_end_ignores_untracked_spans(self, mock_profiling_context):
        processor = _processor()

        span = MagicMock(spec=Span)
        span_ctx = SpanContext(trace_id=123, span_id=456, is_remote=False)
        span.get_span_context.return_value = span_ctx

        processor.on_end(span)

        mock_profiling_context.return_value._pause_after.assert_not_called()  # noqa: SLF001

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
        assert span.attributes.get("splunk.snapshot.profiling") == (None if failure == "start" else True)
        assert timer.pause_count == 1

        timer.fail_start = False
        timer.fail_pause = False
        span = tracer.start_span("next request", context=context)
        span.end()
        assert span.attributes["splunk.snapshot.profiling"] is True
        assert timer.pause_count == 2
    finally:
        timer.fail_start = False
        timer.fail_pause = False
        provider.shutdown()


@pytest.mark.parametrize("callback", ["on_start", "on_end"])
@pytest.mark.usefixtures("profiling_timer_type", "failed_profiler_diagnostics")
def test_snapshot_callback_contains_span_and_logging_failures(callback, caplog):
    class FakeSpan:
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


def test_pause_error_logging_can_start_a_selected_span():
    script = dedent("""
        import logging
        from opentelemetry import baggage
        from opentelemetry._logs import NoOpLoggerProvider
        from opentelemetry.context import Context
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from splunk_otel.callgraphs import CallgraphsSpanProcessor
        from splunk_otel.profile import _IntervalTimer

        provider = TracerProvider(shutdown_on_exit=False)
        provider.add_span_processor(CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test")))
        tracer = provider.get_tracer("test")
        selected = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
        pause_timer = _IntervalTimer.pause_after
        attempts = []
        nested_spans = []

        def fail_first_pause(timer, seconds):
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("timer pause failed")
            pause_timer(timer, seconds)

        class TracingLogHandler(logging.Handler):
            def emit(self, record):
                if not nested_spans:
                    nested_spans.append(None)
                    with tracer.start_as_current_span("log handler", context=selected) as span:
                        nested_spans[0] = span

        _IntervalTimer.pause_after = fail_first_pause
        logging.getLogger().addHandler(TracingLogHandler())
        try:
            with tracer.start_as_current_span("request", context=selected):
                pass
            assert len(nested_spans) == 1
            assert nested_spans[0].attributes["splunk.snapshot.profiling"] is True
        finally:
            provider.shutdown()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_snapshot_spans_skip_profiling_after_sampler_exit(monkeypatch, caplog):
    processor = CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test"))
    timer = processor._profiler._timer  # noqa: SLF001
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("test")
    selected = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

    def failed_sampling_wait(_seconds):
        message = "sampling wait failed"
        raise RuntimeError(message)

    monkeypatch.setattr(timer._stop_event, "wait", failed_sampling_wait)  # noqa: SLF001
    try:
        with tracer.start_as_current_span("first request", context=selected):
            timer.thread.join(2)
            assert not timer.thread.is_alive()
        with tracer.start_as_current_span("next request", context=selected) as span:
            assert span.attributes.get("splunk.snapshot.profiling") is None
        assert not timer.running
        assert "sampling wait failed" in caplog.text
    finally:
        provider.shutdown()


def test_snapshot_start_recovers_after_thread_launch_failure(monkeypatch):
    processor = CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test"))
    timer = processor._profiler._timer  # noqa: SLF001
    launch_sampler = timer.thread.start
    attempts = []
    sampled = Event()

    def sampler_launch():
        attempts.append(True)
        if len(attempts) == 1:
            message = "sampler launch failed"
            raise RuntimeError(message)
        launch_sampler()

    monkeypatch.setattr(timer.thread, "start", sampler_launch)
    monkeypatch.setattr(timer, "target", sampled.set)
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("test")
    selected = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
    try:
        with tracer.start_as_current_span("failed launch", context=selected) as span:
            assert span.attributes.get("splunk.snapshot.profiling") is None
            assert not sampled.is_set()
        with tracer.start_as_current_span("next request", context=selected) as span:
            assert span.attributes["splunk.snapshot.profiling"] is True
            assert sampled.wait(2)
    finally:
        provider.shutdown()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires fork")
def test_snapshot_configured_before_fork_profiles_first_worker_span():
    script = dedent("""
        import os
        import signal
        from threading import Event
        from opentelemetry import baggage
        from opentelemetry.context import Context
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from splunk_otel.callgraphs import CallgraphsSpanProcessor

        class ProfilingLogger:
            def __init__(self):
                self.sampled = Event()
            def emit(self, record):
                assert record.log_record.attributes["profiling.instrumentation.source"] == "snapshot"
                self.sampled.set()

        logger = ProfilingLogger()
        provider = TracerProvider(shutdown_on_exit=False)
        provider.add_span_processor(CallgraphsSpanProcessor(Resource({}), logger, sampling_interval=1))
        tracer = provider.get_tracer("test")
        selected = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
        child = os.fork()
        if child == 0:
            signal.alarm(5)
            try:
                with tracer.start_as_current_span("first worker request", context=selected) as span:
                    assert span.attributes.get("splunk.snapshot.profiling") is True
                    assert logger.sampled.wait(2), "first selected worker span did not emit a profile"
            finally:
                provider.shutdown()
            os._exit(0)
        try:
            _, status = os.waitpid(child, 0)
            assert status == 0, f"worker exited with {os.waitstatus_to_exitcode(status)}"
        finally:
            provider.shutdown()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_concurrent_snapshot_request_is_sampled_after_delayed_launch(monkeypatch):
    class ProfilingLogger:
        def __init__(self):
            self.records = []
            self.sampled = Event()

        def emit(self, record):
            self.records.append(record.log_record)
            self.sampled.set()

    logger = ProfilingLogger()
    processor = CallgraphsSpanProcessor(Resource({}), logger)
    timer = processor._profiler._timer  # noqa: SLF001
    launch_sampler = timer.thread.start
    launch_started = Event()
    release_launch = Event()
    release_first_request = Event()
    first_request_active = Event()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("test")
    selected = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

    def delayed_sampler_launch():
        launch_started.set()
        assert release_launch.wait(5)
        launch_sampler()

    def first_request():
        with tracer.start_as_current_span("first request", context=selected):
            first_request_active.set()
            release_first_request.wait(5)

    monkeypatch.setattr(timer.thread, "start", delayed_sampler_launch)
    request = Thread(target=first_request, daemon=True)
    request.start()
    try:
        assert launch_started.wait(2)
        with tracer.start_as_current_span("concurrent request", context=selected) as span:
            release_launch.set()
            assert first_request_active.wait(2)
            assert logger.sampled.wait(2)
            profile = profile_pb2.Profile()
            profile.ParseFromString(gzip.decompress(base64.b64decode(logger.records[0].body)))
            strings = profile.string_table
            trace_ids = {
                int(strings[label.str], 16)
                for sample in profile.sample
                for label in sample.label
                if strings[label.key] == "trace_id"
            }
            assert span.get_span_context().trace_id in trace_ids
    finally:
        release_launch.set()
        release_first_request.set()
        request.join(2)
        provider.shutdown()
    assert not request.is_alive()


@pytest.mark.parametrize("handler_fails", [False, True])
def test_failed_snapshot_start_cleans_up_before_diagnostic(monkeypatch, handler_fails):
    processor = CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test"))
    timer = processor._profiler._timer  # noqa: SLF001
    launch_sampler = timer.thread.start
    attempts = []
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("test")
    selected = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())

    def fail_first_sampler_launch():
        attempts.append(True)
        if len(attempts) == 1:
            message = "sampler launch failed"
            raise RuntimeError(message)
        launch_sampler()

    class TracingLogHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.handled = False
            self.tracked_before_diagnostic = None

        def emit(self, record):
            if not self.handled:
                self.handled = True
                self.tracked_before_diagnostic = len(processor._span_id_to_trace_id)  # noqa: SLF001
                with tracer.start_as_current_span("log handler", context=selected):
                    pass
                if handler_fails:
                    message = "diagnostic handler failed"
                    raise FileNotFoundError(message)

    handler = TracingLogHandler()
    logger = logging.getLogger("splunk_otel")
    logger.addHandler(handler)
    monkeypatch.setattr(timer.thread, "start", fail_first_sampler_launch)
    try:
        with tracer.start_as_current_span("failed launch", context=selected) as span:
            assert span.attributes.get("splunk.snapshot.profiling") is None
        assert handler.handled
        assert handler.tracked_before_diagnostic == 0
        assert not processor._span_id_to_trace_id  # noqa: SLF001
        assert timer.thread.is_alive()
        assert timer.pause_at is not None
    finally:
        logger.removeHandler(handler)
        handler.close()
        provider.shutdown()
