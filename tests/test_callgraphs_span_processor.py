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

from splunk_otel.callgraphs import CallgraphsSpanProcessor
from splunk_otel.callgraphs.span_processor import _should_process_context
from splunk_otel.profile import _IntervalTimer


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
        assert timer.pause_count == (1 if failure == "pause" else 0)

        timer.fail_start = False
        timer.fail_pause = False
        span = tracer.start_span("next request", context=context)
        span.end()
        assert span.attributes["splunk.snapshot.profiling"] is True
        assert timer.pause_count == (2 if failure == "pause" else 1)
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


def test_snapshot_start_during_shutdown_does_not_block():
    # Isolate the threads so a deadlock fails without blocking the test process.
    script = dedent("""
        from threading import Event, Thread, current_thread
        from opentelemetry import baggage
        from opentelemetry._logs import NoOpLoggerProvider
        from opentelemetry.context import Context
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from splunk_otel import profile
        from splunk_otel.profile import _IntervalTimer
        from splunk_otel.callgraphs import CallgraphsSpanProcessor

        sample_started = Event()
        release_sample = Event()
        shutdown_waiting = Event()
        request_finished = Event()
        timers = []
        request_spans = []
        join_callers = []

        def profiling_timer(interval_millis, target):
            def paused_profile_sample():
                sample_started.set()
                assert release_sample.wait(5), "sample was not released"
                target()
            timer = _IntervalTimer(interval_millis, paused_profile_sample)
            timers.append(timer)
            return timer

        profile._IntervalTimer = profiling_timer
        provider = TracerProvider(shutdown_on_exit=False)
        processor = CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test"))
        provider.add_span_processor(processor)
        tracer = provider.get_tracer("test")
        context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
        first_span = tracer.start_span("first request", context=context)
        (timer,) = timers
        sampler_join = timer.thread.join
        shutdown_thread = Thread(target=provider.shutdown, daemon=True)

        def join_sampler(timeout=None):
            join_callers.append(current_thread())
            if current_thread() is shutdown_thread:
                shutdown_waiting.set()
            sampler_join(timeout)

        timer.thread.join = join_sampler

        def start_request():
            try:
                with tracer.start_as_current_span("request during shutdown", context=context) as span:
                    request_spans.append(span)
            finally:
                request_finished.set()

        request_thread = Thread(target=start_request, daemon=True)
        try:
            assert sample_started.wait(2), "sampler did not start"
            shutdown_thread.start()
            assert shutdown_waiting.wait(2), "shutdown did not wait for the sample"
            request_thread.start()
            assert request_finished.wait(2), "request waited for the in-flight sample"
            assert shutdown_thread.is_alive(), "shutdown should still be waiting for the sample"
            assert join_callers == [shutdown_thread], "request attempted to join the sampler"
            release_sample.set()
            request_thread.join(2)
            shutdown_thread.join(2)
            assert not request_thread.is_alive(), "snapshot startup blocked the request"
            assert not shutdown_thread.is_alive(), "snapshot shutdown blocked"
            assert not timer.thread.is_alive(), "sampler did not stop"
            (span,) = request_spans
            assert span.attributes.get("splunk.snapshot.profiling") is None
            first_span.end()
        finally:
            release_sample.set()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("retry_succeeds", [False, True])
def test_concurrent_spans_only_report_successful_sampler_launch(monkeypatch, retry_succeeds):
    timers = []

    def profiling_timer(interval_millis, target):
        timer = _IntervalTimer(interval_millis, target)
        timers.append(timer)
        return timer

    monkeypatch.setattr("splunk_otel.profile._IntervalTimer", profiling_timer)
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(CallgraphsSpanProcessor(Resource({}), NoOpLoggerProvider().get_logger("test")))
    tracer = provider.get_tracer("test")
    context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
    (timer,) = timers
    launch_sampler = timer.thread.start
    launch_started = Event()
    release_launch = Event()
    second_request_started = Event()
    sampled = Event()
    attempts = []
    spans = {}
    sample = timer.target

    def profile_sample():
        sampled.set()
        sample()

    def sampler_launch():
        attempts.append(True)
        if len(attempts) == 1:
            launch_started.set()
            assert release_launch.wait(5), "launch was not released"
        elif retry_succeeds:
            launch_sampler()
            return
        message = "sampler launch failed"
        raise RuntimeError(message)

    def start_request(name):
        if name == "second":
            second_request_started.set()
        with tracer.start_as_current_span(name, context=context) as span:
            spans[name] = span

    monkeypatch.setattr(timer.thread, "start", sampler_launch)
    monkeypatch.setattr(timer, "target", profile_sample)
    first = Thread(target=start_request, args=("first",), daemon=True)
    second = Thread(target=start_request, args=("second",), daemon=True)
    try:
        first.start()
        assert launch_started.wait(2)
        second.start()
        assert second_request_started.wait(2)
        assert not timer.running, "timer reported running before thread launch succeeded"
        release_launch.set()
        first.join(2)
        second.join(2)
        assert not first.is_alive()
        assert not second.is_alive()
        assert spans["first"].attributes.get("splunk.snapshot.profiling") is None
        assert spans["second"].attributes.get("splunk.snapshot.profiling") == (True if retry_succeeds else None)
        assert len(attempts) == 2
        if retry_succeeds:
            assert sampled.wait(2), "successful launch did not produce a live sampler"
        else:
            assert not sampled.is_set()
    finally:
        release_launch.set()
        first.join(2)
        if second.ident is not None:
            second.join(2)
        provider.shutdown()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires fork")
@pytest.mark.parametrize("parent_state", ["before_first_span", "locks_held", "shutdown", "reset_failure"])
def test_forked_child_snapshot_profiling(parent_state):
    script = dedent("""
        import base64
        import gzip
        import os
        import signal
        import sys
        import traceback
        from threading import Event, Thread
        from opentelemetry import baggage
        from opentelemetry.context import Context
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from splunk_otel import profile_pb2
        from splunk_otel.callgraphs import CallgraphsSpanProcessor

        class ProfilingLogger:
            def __init__(self):
                self.record = None
                self.sampled = Event()
            def emit(self, record):
                self.record = record.log_record
                self.sampled.set()

        logger = ProfilingLogger()
        provider = TracerProvider(shutdown_on_exit=False)
        processor = CallgraphsSpanProcessor(Resource({}), logger, sampling_interval=1)
        provider.add_span_processor(processor)
        tracer = provider.get_tracer("test")
        context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
        parent_state = sys.argv[1]
        locks_held = Event()
        release_locks = Event()
        holder = parent_span = None

        def hold_profiler_locks():
            with processor._lock, processor._profiler._timer._lock:
                locks_held.set()
                release_locks.wait()

        def failed_profiler_factory():
            raise RuntimeError("worker initialization failed")

        try:
            if parent_state == "locks_held":
                parent_span = tracer.start_span("parent request", context=context)
                holder = Thread(target=hold_profiler_locks, daemon=True)
                holder.start()
                assert locks_held.wait(2), "parent did not acquire the profiler locks"
            elif parent_state == "shutdown":
                processor.shutdown()
            elif parent_state == "reset_failure":
                processor._new_profiler = failed_profiler_factory

            child = os.fork()
            if child == 0:
                signal.alarm(5)
                try:
                    logger.record = None
                    logger.sampled = Event()
                    assert not processor._span_id_to_trace_id, "child retained parent span bookkeeping"
                    with tracer.start_as_current_span("child request", context=context) as span:
                        if parent_state in {"shutdown", "reset_failure"}:
                            assert span.attributes.get("splunk.snapshot.profiling") is None
                        else:
                            assert span.attributes.get("splunk.snapshot.profiling") is True
                            assert logger.sampled.wait(2), "first selected child span did not emit a profile"
                            profile = profile_pb2.Profile()
                            profile.ParseFromString(gzip.decompress(base64.b64decode(logger.record.body)))
                            strings = profile.string_table
                            trace_ids = {int(strings[label.str], 16) for sample in profile.sample
                                         for label in sample.label if strings[label.key] == "trace_id"}
                            assert trace_ids == {span.get_span_context().trace_id}
                    if parent_span is not None:
                        parent_span.end()
                    provider.shutdown()
                except Exception:
                    traceback.print_exc()
                    os._exit(1)
                os._exit(0)

            release_locks.set()
            _, status = os.waitpid(child, 0)
            assert status == 0, f"forked child exited with {os.waitstatus_to_exitcode(status)}"
            if parent_state != "shutdown":
                logger.sampled.clear()
                with tracer.start_as_current_span("next parent request", context=context):
                    assert logger.sampled.wait(2), "parent profiler stopped emitting after fork"
        finally:
            release_locks.set()
            if holder is not None:
                holder.join(2)
                assert not holder.is_alive(), "parent profiler remained blocked"
            if parent_span is not None:
                parent_span.end()
            provider.shutdown()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, parent_state],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
