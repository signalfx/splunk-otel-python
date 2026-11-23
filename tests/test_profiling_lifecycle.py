# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from textwrap import dedent
from threading import Event

import pytest
from opentelemetry import baggage, trace
from opentelemetry.context import Context
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk.trace import TracerProvider

from splunk_otel._environment_profiling import _configure_environment_profiling
from splunk_otel.configurator import SplunkConfigurator
from splunk_otel.distro import EnvironmentConfiguration
from splunk_otel.env import Env


@pytest.fixture
def snapshot_provider(monkeypatch):
    provider = TracerProvider(shutdown_on_exit=False)
    original_propagator = get_global_textmap()
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    yield provider
    provider.shutdown()
    set_global_textmap(original_propagator)


def _configure_snapshots(probability, sampling_interval=10):
    env = Env(
        {
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true",
            "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY": str(probability),
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": str(sampling_interval),
        }
    )
    EnvironmentConfiguration(env).configure()
    _configure_environment_profiling(env)


def _local_snapshot_selection():
    context = get_global_textmap().extract({}, context=Context())
    return baggage.get_baggage("splunk.trace.snapshot.volume", context)


@pytest.mark.usefixtures("profiling_timer_type", "snapshot_provider")
def test_duplicate_environment_setup_keeps_active_selection(profiling_controller):
    reported = []
    profiling_controller.subscribe(reported.append)
    _configure_snapshots(1.0)

    _configure_snapshots(0.0)

    assert reported[-1].selection_probability == 1.0
    assert _local_snapshot_selection() == "highest"


@pytest.mark.usefixtures("profiling_timer_type", "snapshot_provider")
def test_stopping_snapshots_disables_local_selection(profiling_controller):
    _configure_snapshots(1.0)
    assert _local_snapshot_selection() == "highest"

    profiling_controller.stop_snapshot()

    assert _local_snapshot_selection() is None


@pytest.mark.parametrize("repeated_callgraphs", ["selection_probability: 1.0", "selection_probability: 0.5", None])
@pytest.mark.usefixtures("profiling_timer_type", "snapshot_provider")
def test_repeated_yaml_setup_keeps_active_snapshot_selection(
    tmp_path, monkeypatch, profiling_controller, repeated_callgraphs
):
    config_file = tmp_path / "profiling.yaml"
    monkeypatch.setenv("OTEL_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "logging")
    base_config = 'file_format: "1.0"\npropagator:\n  composite_list: tracecontext,baggage\n'
    profiling_config = "distribution:\n  splunk:\n    profiling:\n      callgraphs:\n        "
    config_file.write_text(base_config + profiling_config + "selection_probability: 1.0\n")
    reported = []
    profiling_controller.subscribe(reported.append)
    configurator = SplunkConfigurator()
    configurator.configure()
    assert _local_snapshot_selection() == "highest"

    config_file.write_text(base_config + (profiling_config + repeated_callgraphs + "\n" if repeated_callgraphs else ""))
    configurator.configure()

    assert reported[-1].selection_probability == 1.0
    assert _local_snapshot_selection() == "highest"
    context = get_global_textmap().extract(
        {
            "traceparent": "00-12345678901234567890123456789012-1234567890123456-01",
            "baggage": "splunk.trace.snapshot.volume=off",
        },
        context=Context(),
    )
    assert trace.get_current_span(context).get_span_context().is_remote
    assert baggage.get_baggage("splunk.trace.snapshot.volume", context) == "off"


def test_delayed_provider_shutdown_does_not_clear_restarted_snapshot(
    snapshot_provider, profiling_controller, profiling_timer_type, monkeypatch
):
    reported = []
    profiling_controller.subscribe(reported.append)
    _configure_snapshots(1.0)
    (old_timer,) = profiling_timer_type.instances
    stop_timer = old_timer.stop
    sampler_stopped = Event()
    finish_shutdown = Event()

    def _delayed_timer_stop():
        stop_timer()
        if not sampler_stopped.is_set():
            sampler_stopped.set()
            assert finish_shutdown.wait(5), "provider shutdown was not released"

    monkeypatch.setattr(old_timer, "stop", _delayed_timer_stop)
    with ThreadPoolExecutor(max_workers=1) as executor:
        shutdown = executor.submit(snapshot_provider.shutdown)
        try:
            assert sampler_stopped.wait(5), "provider did not stop the sampler"
            profiling_controller.stop_snapshot()
            _configure_snapshots(0.0, sampling_interval=20)
            span = snapshot_provider.get_tracer("test").start_span(
                "selected request", context=baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
            )
            span.end()
            new_timer = profiling_timer_type.instances[-1]
            assert new_timer is not old_timer
            assert new_timer.started
        finally:
            finish_shutdown.set()
        shutdown.result(timeout=5)

    assert reported[-1].snapshot_interval == 20
    assert reported[-1].selection_probability == 0.0
    assert _local_snapshot_selection() == "off"
    profiling_controller.stop_snapshot()
    assert new_timer.stopped
    assert reported[-1].snapshot_interval is None
    assert _local_snapshot_selection() is None


def test_snapshot_restarts_attach_one_processor_per_provider(
    snapshot_provider, profiling_controller, profiling_timer_type
):
    attached = []
    add_span_processor = snapshot_provider.add_span_processor

    def _record_span_processor(processor):
        attached.append(processor)
        add_span_processor(processor)

    snapshot_provider.add_span_processor = _record_span_processor
    for probability, interval in ((1.0, 10), (0.0, 20), (1.0, 30), (0.0, 40)):
        _configure_snapshots(probability, interval)
        assert _local_snapshot_selection() == ("highest" if probability else "off")
        span = snapshot_provider.get_tracer("test").start_span(
            "selected request", context=baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
        )
        span.end()
        assert span.attributes["splunk.snapshot.profiling"] is True
        timer = profiling_timer_type.instances[-1]
        assert timer.started
        assert timer.interval_millis == interval
        profiling_controller.stop_snapshot()

    assert len(attached) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires fork")
@pytest.mark.parametrize("snapshots_enabled", [False, True])
def test_child_can_start_profiling_after_parent(snapshots_enabled):
    script = dedent("""
        import os
        import select
        import signal
        from threading import Event
        from opentelemetry import baggage
        from opentelemetry.context import Context
        from opentelemetry.sdk.trace import TracerProvider
        from splunk_otel import _environment_profiling
        from splunk_otel.env import Env
        from splunk_otel.profile import start_profiling

        class ProfilingLogger:
            def __init__(self):
                self.sampled = Event()
                self.snapshot_sampled = Event()
            def emit(self, record):
                if record.log_record.attributes["profiling.instrumentation.source"] == "snapshot":
                    self.snapshot_sampled.set()
                else:
                    self.sampled.set()

        logger = ProfilingLogger()
        _environment_profiling._get_profiling_logger = lambda: logger
        provider = TracerProvider(shutdown_on_exit=False)
        attached = []
        add_span_processor = provider.add_span_processor
        def record_span_processor(processor):
            attached.append(processor)
            add_span_processor(processor)
        provider.add_span_processor = record_span_processor
        _environment_profiling.trace.get_tracer_provider = lambda: provider
        snapshots = Env({"SPLUNK_SNAPSHOT_PROFILER_ENABLED": "true", "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "2"})
        env = Env({"SPLUNK_PROFILER_CALL_STACK_INTERVAL": "2"})
        parent_context = start_profiling(env)
        assert parent_context is not None
        assert logger.sampled.wait(2)
        if SNAPSHOTS_ENABLED:
            _environment_profiling._configure_environment_profiling(snapshots)
        reader, writer = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                os.close(reader)
                logger.sampled = Event()
                logger.snapshot_sampled = Event()
                child_context = start_profiling(env)
                live = child_context is not None and child_context is not parent_context and logger.sampled.wait(2)
                if SNAPSHOTS_ENABLED:
                    context = baggage.set_baggage("splunk.trace.snapshot.volume", "highest", Context())
                    with provider.get_tracer("test").start_as_current_span("child request", context=context):
                        live = live and len(attached) == 1 and logger.snapshot_sampled.wait(2)
                    provider.shutdown()
                if live:
                    child_context.stop()
                os.write(writer, b"live" if live else b"no sampler")
            finally:
                os._exit(0)
        os.close(writer)
        try:
            ready, _, _ = select.select([reader], [], [], 5)
            if not ready:
                os.kill(child, signal.SIGKILL)
            _, status = os.waitpid(child, 0)
            assert ready, "child profiler startup hung"
            assert status == 0
            assert os.read(reader, 64) == b"live"
        finally:
            os.close(reader)
            provider.shutdown()
            parent_context.stop()
    """).replace("SNAPSHOTS_ENABLED", repr(snapshots_enabled))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
