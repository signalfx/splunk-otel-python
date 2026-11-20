# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import FrozenInstanceError

import pytest
from opentelemetry._logs import NoOpLoggerProvider
from opentelemetry.sdk.resources import Resource

from splunk_otel._profiling import ProfilingSettings

RESOURCE = Resource({})
LOGGER = NoOpLoggerProvider().get_logger("test")


pytestmark = pytest.mark.usefixtures("profiling_timer_type")


class FakeTracerProvider:
    def __init__(self):
        self.processors = []
        self.fail_attach = False

    def add_span_processor(self, processor):
        self.processors.append(processor)
        if self.fail_attach:
            message = "attachment failed"
            raise RuntimeError(message)


@pytest.fixture(autouse=True)
def selected_probabilities(monkeypatch):
    received = []
    monkeypatch.setattr("splunk_otel._profiling._configure_callgraphs_propagator", received.append)
    return received


@pytest.fixture
def tracer_provider():
    return FakeTracerProvider()


@pytest.fixture
def reported_settings(profiling_controller):
    received = []
    profiling_controller.subscribe(received.append)
    return received


def test_late_subscriber_receives_current_immutable_settings(profiling_controller):
    profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=1000)
    received = []
    profiling_controller.subscribe(received.append)

    assert received == [ProfilingSettings(cpu_interval=1000)]
    with pytest.raises(FrozenInstanceError):
        received[0].cpu_interval = 2000
    profiling_controller.stop_continuous()
    assert received == [ProfilingSettings(cpu_interval=1000), ProfilingSettings()]


def test_shutdown_stops_both_owned_profilers(
    profiling_controller, profiling_timer_type, reported_settings, tracer_provider
):
    profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)
    profiling_controller.start_snapshot(
        tracer_provider=tracer_provider,
        resource=RESOURCE,
        logger=LOGGER,
        sampling_interval=17,
        selection_probability=0.2,
    )
    continuous_timer, snapshot_timer = profiling_timer_type.instances
    assert continuous_timer.interval_millis == 250
    assert snapshot_timer.interval_millis == 17
    assert reported_settings[-1] == ProfilingSettings(250, 17, 0.2)

    profiling_controller.shutdown()
    profiling_controller.shutdown()

    assert not continuous_timer.started
    assert continuous_timer.stop_count == 1
    assert snapshot_timer.stopped
    assert reported_settings[-1] == ProfilingSettings(selection_probability=0.2)


def test_failed_constructor_does_not_report_enabled(profiling_controller, profiling_timer_type, reported_settings):
    profiling_timer_type.fail_construction = True

    with pytest.raises(RuntimeError, match="timer construction failed"):
        profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)

    assert not profiling_timer_type.instances
    assert reported_settings == [ProfilingSettings()]


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failed_start_cleans_up_without_reporting_enabled(
    profiling_controller, profiling_timer_type, reported_settings, cleanup_fails, caplog
):
    profiling_timer_type.fail_start = True
    profiling_timer_type.fail_stop = cleanup_fails

    result = profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)

    assert result is None
    (timer,) = profiling_timer_type.instances
    assert timer.stopped == (not cleanup_fails)
    assert reported_settings == [ProfilingSettings()]
    assert "Failed to start profiling timer" in caplog.text
    if cleanup_fails:
        assert "Failed to stop profiling timer" in caplog.text


@pytest.mark.parametrize("profiling_mode", ["continuous", "snapshot"])
def test_failed_shutdown_registration_does_not_create_profiler(
    profiling_controller,
    profiling_timer_type,
    reported_settings,
    tracer_provider,
    selected_probabilities,
    monkeypatch,
    profiling_mode,
):
    def _fake_register_shutdown(_callback):
        message = "registration failed"
        raise RuntimeError(message)

    monkeypatch.setattr("splunk_otel._profiling.atexit.register", _fake_register_shutdown)

    if profiling_mode == "continuous":
        with pytest.raises(RuntimeError, match="registration failed"):
            profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)
    else:
        with pytest.raises(RuntimeError, match="registration failed"):
            profiling_controller.start_snapshot(
                tracer_provider=tracer_provider,
                resource=RESOURCE,
                logger=LOGGER,
                sampling_interval=17,
                selection_probability=0.2,
            )

    assert not profiling_timer_type.instances
    assert not tracer_provider.processors
    assert not selected_probabilities
    assert reported_settings == [ProfilingSettings()]


@pytest.mark.parametrize("failure", ["construction", "attachment", "selection", "cleanup"])
def test_failed_snapshot_setup_keeps_continuous_settings(
    profiling_controller,
    profiling_timer_type,
    failure,
    reported_settings,
    tracer_provider,
    selected_probabilities,
    monkeypatch,
    caplog,
):
    profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)
    (continuous_timer,) = profiling_timer_type.instances
    continuous_timer.fail_stop = False
    profiling_timer_type.fail_construction = failure == "construction"
    profiling_timer_type.fail_stop = failure == "cleanup"
    tracer_provider.fail_attach = failure in {"attachment", "cleanup"}

    def _fake_configure_callgraphs_propagator(probability):
        selected_probabilities.append(probability)
        if failure == "selection":
            message = "selection failed"
            raise RuntimeError(message)

    monkeypatch.setattr(
        "splunk_otel._profiling._configure_callgraphs_propagator", _fake_configure_callgraphs_propagator
    )

    with pytest.raises(RuntimeError, match="failed"):
        profiling_controller.start_snapshot(
            tracer_provider=tracer_provider,
            resource=RESOURCE,
            logger=LOGGER,
            sampling_interval=17,
            selection_probability=0.2,
        )

    if failure == "construction":
        assert not tracer_provider.processors
    else:
        snapshot_timer = profiling_timer_type.instances[1]
        assert snapshot_timer.stopped == (failure != "cleanup")
    if failure == "cleanup":
        assert "Failed to stop profiling timer" in caplog.text
    assert selected_probabilities == ([0.2] if failure == "selection" else [])
    assert reported_settings[-1] == ProfilingSettings(cpu_interval=250)


def test_external_stop_notifies_once_and_old_context_cannot_clear_new_state(profiling_controller):
    received = []
    profiling_controller.subscribe(received.append)
    old_context = profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)
    old_context.stop()
    profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=500)
    old_context.stop()

    assert received == [
        ProfilingSettings(),
        ProfilingSettings(cpu_interval=250),
        ProfilingSettings(),
        ProfilingSettings(cpu_interval=500),
    ]


def test_external_processor_shutdown_updates_active_settings(profiling_controller, reported_settings, tracer_provider):
    profiling_controller.start_snapshot(
        tracer_provider=tracer_provider,
        resource=RESOURCE,
        logger=LOGGER,
        sampling_interval=17,
        selection_probability=0.2,
    )
    (processor,) = tracer_provider.processors
    processor.shutdown()
    assert reported_settings[-1] == ProfilingSettings(selection_probability=0.2)


@pytest.mark.parametrize("failure", ["continuous", "snapshot"])
def test_failed_stop_keeps_active_state_and_shutdown_still_stops_other_mode(
    profiling_controller, profiling_timer_type, reported_settings, tracer_provider, failure, caplog
):
    profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)
    profiling_controller.start_snapshot(
        tracer_provider=tracer_provider,
        resource=RESOURCE,
        logger=LOGGER,
        sampling_interval=17,
        selection_probability=0.2,
    )
    continuous_timer, snapshot_timer = profiling_timer_type.instances
    continuous_timer.fail_stop = failure == "continuous"
    snapshot_timer.fail_stop = failure == "snapshot"
    try:
        profiling_controller.shutdown()
        assert snapshot_timer.stopped == (failure == "continuous")
        assert continuous_timer.started == (failure == "continuous")
        assert reported_settings[-1] == ProfilingSettings(
            cpu_interval=250 if failure == "continuous" else None,
            snapshot_interval=17 if failure == "snapshot" else None,
            selection_probability=0.2,
        )
        assert "Failed to stop profiling timer" in caplog.text
    finally:
        continuous_timer.fail_stop = False
        snapshot_timer.fail_stop = False


def test_listener_failure_does_not_change_profiler_outcome(profiling_controller, profiling_timer_type, caplog):
    def _fake_state_listener(_settings):
        message = "listener failed"
        raise RuntimeError(message)

    profiling_controller.subscribe(_fake_state_listener)
    profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)
    (timer,) = profiling_timer_type.instances
    assert timer.started
    assert "Profiler state listener failed" in caplog.text
    profiling_controller.stop_continuous()
    assert not timer.started
    received = []
    profiling_controller.subscribe(received.append)
    assert received == [ProfilingSettings()]


def test_duplicate_start_returns_original_profiler_and_warns(
    profiling_controller, profiling_timer_type, reported_settings, caplog
):
    context = profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=250)

    repeated_context = profiling_controller.start_continuous(resource=RESOURCE, logger=LOGGER, sampling_interval=500)

    assert repeated_context is context
    (timer,) = profiling_timer_type.instances
    assert timer.started
    assert timer.interval_millis == 250
    assert reported_settings == [ProfilingSettings(), ProfilingSettings(cpu_interval=250)]
    assert "Continuous profiling is already configured; ignoring duplicate start" in caplog.text


def test_duplicate_snapshot_start_does_not_change_selection(
    profiling_controller, profiling_timer_type, reported_settings, tracer_provider, selected_probabilities, caplog
):
    profiling_controller.start_snapshot(
        tracer_provider=tracer_provider,
        resource=RESOURCE,
        logger=LOGGER,
        sampling_interval=17,
        selection_probability=0.2,
    )
    profiling_controller.start_snapshot(
        tracer_provider=tracer_provider,
        resource=RESOURCE,
        logger=LOGGER,
        sampling_interval=23,
        selection_probability=0.6,
    )

    (timer,) = profiling_timer_type.instances
    assert len(tracer_provider.processors) == 1
    assert not timer.stopped
    assert timer.interval_millis == 17
    assert selected_probabilities == [0.2]
    assert reported_settings == [
        ProfilingSettings(),
        ProfilingSettings(snapshot_interval=17, selection_probability=0.2),
    ]
    assert "Snapshot profiling is already configured; ignoring duplicate start" in caplog.text
