import base64
import gzip
import json
import random
import time
from contextlib import ExitStack
from threading import Event, Thread
from collections import OrderedDict
from os.path import abspath, dirname

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry._logs import Logger
from opentelemetry import baggage, trace
from opentelemetry.context import attach, detach
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExportResult
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    get_current_span,
    set_span_in_context,
)
from splunk_otel import profile_pb2
from splunk_otel.profile import (
    _get_line,
    _IntervalTimer,
    _pb_profile_to_str,
    _ProfileScraper,
    _stacktraces_to_cpu_profile,
    _start_continuous_profiling,
    _StringTable,
)


@pytest.fixture
def stacktraces_fixture():
    return load_json("stacktraces.in.json")


@pytest.fixture
def thread_states_fixture():
    out = {}
    og = load_json("thread_states.in.json")
    for k, v in og.items():
        out[int(k)] = v
    return out


@pytest.fixture
def pb_profile_fixture():
    return load_json("pb_profile.out.json")


def load_json(fname):
    parent_dir = dirname(abspath(__file__))
    with open(f"{parent_dir}/fixtures/{fname}") as f:
        return json.load(f)


def test_basic_proto_serialization():
    # noinspection PyUnresolvedReferences
    profile = profile_pb2.Profile()
    serialized = _pb_profile_to_str(profile)
    decoded_profile = _pb_profile_from_str(serialized)
    assert profile == decoded_profile


def test_stacktraces_to_cpu_profile(stacktraces_fixture, pb_profile_fixture, thread_states_fixture):
    time_seconds = 1726760000  # corresponds to the timestamp in the fixture
    interval_millis = 100
    profile = _stacktraces_to_cpu_profile(stacktraces_fixture, thread_states_fixture, interval_millis, time_seconds)
    assert pb_profile_fixture == MessageToDict(profile)


def test_get_line():
    line = _get_line(OrderedDict(), _StringTable(), "test", "test", 42)
    assert line.line == 42


def test_get_line_none():
    line = _get_line(OrderedDict(), _StringTable(), "test", "test", None)
    assert line.line == -1


def test_profile_scraper(stacktraces_fixture):
    time_seconds = 1726760000
    logger = _FakeLogger()
    ps = _ProfileScraper(
        Resource({}),
        {},
        100,
        logger,
        collect_stacktraces_func=lambda: stacktraces_fixture,
        time_func=lambda: time_seconds,
    )
    ps.tick()

    log_record = logger.log_records[0].log_record

    assert log_record.timestamp == int(time_seconds * 1e9)
    assert len(MessageToDict(_pb_profile_from_str(log_record.body))) == 4  # sanity check
    assert log_record.attributes["profiling.data.total.frame.count"] == 30


# The "override the current context" stuff for the log record is weird,
# so test it more thorougly
def test_profile_scraper_log_context_overrides_current_span():
    logger = _FakeLogger()
    ps = _ProfileScraper(Resource({}), {}, 100, logger, time_func=lambda: 1726760000)
    span_context = SpanContext(
        trace_id=1,
        span_id=2,
        is_remote=False,
        trace_flags=TraceFlags(0x00),
    )
    token = attach(set_span_in_context(NonRecordingSpan(span_context)))
    try:
        log_record = ps.mk_log_record([])
        # make sure that the fake log emission context set didn't affect "reality"
        assert get_current_span().get_span_context().trace_id == 1
    finally:
        detach(token)

    record = log_record.log_record
    assert record.trace_id == 0
    assert record.span_id == 0
    assert record.trace_flags == TraceFlags(0x01)


def _pb_profile_from_str(stringified: str) -> profile_pb2.Profile:
    byte_array = base64.b64decode(stringified)
    decompressed = gzip.decompress(byte_array)
    out = profile_pb2.Profile()
    out.ParseFromString(decompressed)
    return out


def _do_work(time_ms):
    now = time.time()
    target = now + time_ms / 1000.0

    total = 0.0
    while now < target:
        value = random.random()
        for _ in range(10000):
            value = value + random.random()

        total = total + value

        now = time.time()
        time.sleep(0.01)

    return total


def test_interval_timer_stop_before_start():
    # stop() must not raise RuntimeError when the thread was never started.
    # Old code called thread.join() unconditionally; joining an unstarted
    # thread raises RuntimeError.
    timer = _IntervalTimer(100, lambda: None)
    timer.stop()


def test_interval_timer_stop_interrupts_long_sampling_interval():
    sampled = Event()
    timer = _IntervalTimer(60000, sampled.set)
    timer.start()
    assert sampled.wait(timeout=2)

    stop_thread = Thread(target=timer.stop, daemon=True)
    stop_thread.start()
    stop_thread.join(timeout=2)

    assert not stop_thread.is_alive(), "stop must interrupt the sampling wait"


@pytest.mark.parametrize("pause_state", ["paused", "entering_pause"])
@pytest.mark.parametrize("pause_action", ["stop", "resume"])
def test_interval_timer_stop_or_resume_during_pause(monkeypatch, pause_state, pause_action):
    pause_reached = Event()
    release_pause = Event()
    wakeup_requested = Event()
    resume_requested = Event()
    sampled_while_paused = Event()
    resumed = Event()

    def _fake_sample():
        if pause_reached.is_set():
            if not resume_requested.is_set():
                sampled_while_paused.set()
            resumed.set()
        else:
            timer.pause_after(0)

    timer = _IntervalTimer(0, _fake_sample)
    wakeup_clear = timer.wakeup_event.clear
    wakeup_wait = timer.wakeup_event.wait
    wakeup_set = timer.wakeup_event.set

    def _fake_wakeup_clear():
        if pause_state == "entering_pause":
            pause_reached.set()
            assert release_pause.wait(timeout=5)
        wakeup_clear()

    def _fake_wakeup_wait():
        if pause_state == "paused":
            pause_reached.set()
        return wakeup_wait()

    def _fake_wakeup_set():
        wakeup_set()
        wakeup_requested.set()

    monkeypatch.setattr(timer.wakeup_event, "clear", _fake_wakeup_clear)
    monkeypatch.setattr(timer.wakeup_event, "wait", _fake_wakeup_wait)
    monkeypatch.setattr(timer.wakeup_event, "set", _fake_wakeup_set)
    timer.start()
    try:
        assert pause_reached.wait(timeout=2)
        assert not resumed.is_set(), "sampling must stay paused until resume is requested"
        wakeup_requested.clear()
        if pause_action == "stop":
            stop_thread = Thread(target=timer.stop, daemon=True)
            stop_thread.start()
            assert wakeup_requested.wait(timeout=2)
            release_pause.set()
            stop_thread.join(timeout=2)
            assert not stop_thread.is_alive(), "stop must wake a paused sampler"
        else:
            resume_requested.set()
            timer.start()
            release_pause.set()
            assert resumed.wait(timeout=2), "resume must wake a paused sampler"
        assert not sampled_while_paused.is_set(), "sampling must stay paused until resume is requested"
    finally:
        release_pause.set()
        wakeup_set()
        timer.stop()


def test_interval_timer_stop_waits_for_current_sample(monkeypatch):
    sample_started = Event()
    release_sample = Event()
    stop_waiting = Event()
    lifecycle = []

    def _fake_sample():
        sample_started.set()
        assert release_sample.wait(timeout=5)
        lifecycle.append("sample completed")

    timer = _IntervalTimer(60000, _fake_sample)
    sampler_join = timer.thread.join

    def _fake_sampler_join(timeout=None):
        stop_waiting.set()
        sampler_join(timeout)

    def _stop_timer():
        timer.stop()
        lifecycle.append("stop completed")

    monkeypatch.setattr(timer.thread, "join", _fake_sampler_join)
    timer.start()
    try:
        assert sample_started.wait(timeout=2)
        stop_thread = Thread(target=_stop_timer, daemon=True)
        stop_thread.start()
        assert stop_waiting.wait(timeout=2)
        assert stop_thread.is_alive()
        assert not lifecycle
        release_sample.set()
        stop_thread.join(timeout=2)
        assert not stop_thread.is_alive()
        assert lifecycle == ["sample completed", "stop completed"]
    finally:
        release_sample.set()
        timer.stop()


@pytest.mark.parametrize("profiling_mode", ["continuous", "callgraphs", "callgraphs_without_tracer_provider"])
def test_exit_flushes_final_profile_after_sampling_stops(monkeypatch, profiling_mode):
    shutdown_callbacks = []
    sample_started = Event()
    release_sample = Event()
    stop_waiting = Event()
    exported_records = []
    lifecycle = []
    timers = []

    def _fake_register_shutdown(callback):
        shutdown_callbacks.append(callback)
        return callback

    def _fake_interval_timer(interval_millis, target):
        timer = _IntervalTimer(interval_millis, target)
        timers.append(timer)
        return timer

    class FakeLogExporter:
        def export(self, records):
            exported_records.extend(records)
            lifecycle.append("sample exported")
            return LogRecordExportResult.SUCCESS

        def shutdown(self):
            lifecycle.append("exporter shut down")

    monkeypatch.setattr("splunk_otel.profile._atexit.register", _fake_register_shutdown)
    monkeypatch.setattr("splunk_otel.profile._IntervalTimer", _fake_interval_timer)
    resource = Resource({"service.name": "final-profile-test"})
    tracer_provider = (
        None if profiling_mode == "callgraphs_without_tracer_provider" else TracerProvider(resource=resource)
    )
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(FakeLogExporter(), schedule_delay_millis=60000))
    logger = provider.get_logger("otel.profiling")

    class FakeProfilingLogger:
        def emit(self, record):
            sample_started.set()
            assert release_sample.wait(timeout=5)
            logger.emit(record)
            lifecycle.append("sample emitted")

    active_spans = ExitStack()
    if profiling_mode == "continuous":
        _start_continuous_profiling(resource=resource, interval_millis=60000, logger=FakeProfilingLogger())
    else:
        from splunk_otel._declarative_profiling import _configure_declarative_profiling

        def _fake_get_tracer_provider():
            return tracer_provider if tracer_provider is not None else trace.ProxyTracerProvider()

        def _fake_set_tracer_provider(provider):
            nonlocal tracer_provider
            tracer_provider = provider

        monkeypatch.setattr(trace, "get_tracer_provider", _fake_get_tracer_provider)
        monkeypatch.setattr(trace, "set_tracer_provider", _fake_set_tracer_provider)
        monkeypatch.setattr("splunk_otel._declarative_profiling.create_logger_provider", lambda *_args: provider)
        monkeypatch.setattr(
            "splunk_otel._declarative_profiling._get_profiling_logger", lambda _provider: FakeProfilingLogger()
        )
        monkeypatch.setattr(
            "splunk_otel._declarative_profiling._configure_callgraphs_propagator", lambda _probability: None
        )
        _configure_declarative_profiling({"splunk": {"profiling": {"callgraphs": {"sampling_interval": 1}}}}, resource)
        assert tracer_provider is not None
        active_spans.enter_context(
            tracer_provider.get_tracer("test").start_as_current_span(
                "selected", context=baggage.set_baggage("splunk.trace.snapshot.volume", "highest")
            )
        )
    (timer,) = timers
    sampler_join = timer.thread.join

    def _fake_sampler_join(timeout=None):
        stop_waiting.set()
        sampler_join(timeout)

    def _release_final_sample():
        if stop_waiting.wait(timeout=5):
            release_sample.set()

    monkeypatch.setattr(timer.thread, "join", _fake_sampler_join)
    release_thread = Thread(target=_release_final_sample, daemon=True)
    release_thread.start()
    try:
        assert sample_started.wait(timeout=2)
        assert not exported_records
        for shutdown in reversed(shutdown_callbacks):
            shutdown()
        release_thread.join(timeout=2)
        assert not release_thread.is_alive()
        assert lifecycle == ["sample emitted", "sample exported", "exporter shut down"]
        (record,) = exported_records
        expected_source = "continuous" if profiling_mode == "continuous" else "snapshot"
        assert record.log_record.attributes["profiling.instrumentation.source"] == expected_source
        assert _pb_profile_from_str(record.log_record.body).sample
    finally:
        release_sample.set()
        active_spans.close()
        timer.stop()
        if tracer_provider is not None:
            tracer_provider.shutdown()
        provider.shutdown()
        release_thread.join(timeout=2)


class _FakeLogger(Logger):
    def __init__(self):
        super().__init__("fake-logger")
        self.log_records = []

    # OpenTelemetry 1.45 requires Logger.enabled(); this fake accepts all records.
    def enabled(self, *, context=None, severity_number=None, event_name=None) -> bool:
        return True

    def emit(self, record) -> None:
        self.log_records.append(record)
