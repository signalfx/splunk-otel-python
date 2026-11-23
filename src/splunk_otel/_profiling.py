# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

"""Own the distro's profiler instances and their successfully applied settings."""

from __future__ import annotations

import atexit
import logging
import os
from dataclasses import dataclass, replace
from threading import RLock
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor
from splunk_otel.profile import ProfilingContext
from splunk_otel.propagator import _configure_callgraphs_propagator

if TYPE_CHECKING:
    from collections.abc import Callable

    from opentelemetry._logs import Logger
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfilingSettings:
    cpu_interval: int | None = None
    snapshot_interval: int | None = None
    selection_probability: float = 0.01


class ProfilingController:
    def __init__(self) -> None:
        self._lock = RLock()
        self._continuous: ProfilingContext | None = None
        self._snapshot: CallgraphsSpanProcessor | None = None
        self._snapshot_processors: WeakKeyDictionary[TracerProvider, CallgraphsSpanProcessor] = WeakKeyDictionary()
        self._settings = ProfilingSettings()
        self._listener: Callable[[ProfilingSettings], None] | None = None

    def subscribe(self, listener: Callable[[ProfilingSettings], None]) -> None:
        with self._lock:
            self._listener = listener
            self._notify()

    def start_continuous(
        self, *, resource: Resource, logger: Logger, sampling_interval: int
    ) -> ProfilingContext | None:
        with self._lock:
            if self._continuous is not None:
                _logger.warning("Continuous profiling is already configured; ignoring duplicate start")
                return self._continuous
            self._register_shutdown(self.stop_continuous)
            context = ProfilingContext(
                resource=resource,
                logger=logger,
                interval_millis=sampling_interval,
                on_stop=self._continuous_stopped,
            )
            if not context.start():
                return None
            self._continuous = context
            self._publish(replace(self._settings, cpu_interval=sampling_interval))
            return context

    def start_snapshot(
        self,
        *,
        tracer_provider: TracerProvider,
        resource: Resource,
        logger: Logger,
        sampling_interval: int,
        selection_probability: float,
    ) -> None:
        with self._lock:
            if self._snapshot is not None:
                _logger.warning("Snapshot profiling is already configured; ignoring duplicate start")
                return
            self._register_shutdown(self.stop_snapshot)
            processor = self._snapshot_processors.get(tracer_provider)
            if processor is None:
                processor = CallgraphsSpanProcessor(
                    resource=resource,
                    logger=logger,
                    sampling_interval=sampling_interval,
                    on_shutdown=self._snapshot_stopped,
                )
            else:
                processor.configure(resource=resource, logger=logger, sampling_interval=sampling_interval)
            try:
                if tracer_provider not in self._snapshot_processors:
                    tracer_provider.add_span_processor(processor)
                    self._snapshot_processors[tracer_provider] = processor
                _configure_callgraphs_propagator(selection_probability)
                self._snapshot = processor
            finally:
                if self._snapshot is not processor:
                    processor.shutdown()
            self._publish(
                replace(
                    self._settings,
                    snapshot_interval=sampling_interval,
                    selection_probability=selection_probability,
                )
            )

    def stop_continuous(self) -> None:
        with self._lock:
            context = self._continuous
            if context is not None:
                context.stop()

    def stop_snapshot(self) -> None:
        with self._lock:
            processor = self._snapshot
            if processor is not None:
                processor.shutdown()

    def shutdown(self) -> None:
        self.stop_continuous()
        self.stop_snapshot()

    def _continuous_stopped(self, context: ProfilingContext) -> None:
        with self._lock:
            if self._continuous is context:
                self._continuous = None
                self._publish(replace(self._settings, cpu_interval=None))

    def _snapshot_stopped(self, processor: CallgraphsSpanProcessor) -> None:
        with self._lock:
            if self._snapshot is processor:
                _configure_callgraphs_propagator(None)
                self._snapshot = None
                self._publish(replace(self._settings, snapshot_interval=None))

    def _register_shutdown(self, callback: Callable[[], None]) -> None:
        # Each mode can acquire a new exporter after the other mode has started.
        atexit.unregister(callback)
        atexit.register(callback)

    def after_fork(self) -> None:
        parent_snapshot = self._snapshot
        parent_settings = self._settings
        self._lock = RLock()
        self._continuous = None
        self._snapshot = None
        self._settings = ProfilingSettings()
        # Inherited listeners may use locks held by threads that no longer exist.
        self._listener = None
        _configure_callgraphs_propagator(None)
        for processor in self._snapshot_processors.values():
            enabled = processor.after_fork()
            if processor is parent_snapshot and enabled:
                _configure_callgraphs_propagator(parent_settings.selection_probability)
                self._snapshot = processor
                self._settings = replace(
                    self._settings,
                    snapshot_interval=parent_settings.snapshot_interval,
                    selection_probability=parent_settings.selection_probability,
                )

    def _publish(self, settings: ProfilingSettings) -> None:
        if settings != self._settings:
            self._settings = settings
            self._notify()

    def _notify(self) -> None:
        if self._listener is not None:
            try:
                self._listener(self._settings)
            except Exception:
                _logger.exception("Profiler state listener failed")


profiling_controller = ProfilingController()


def _reset_profiling_after_fork() -> None:
    try:
        profiling_controller.after_fork()
    except Exception:
        _logger.exception("Failed to reset profiling after fork")


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_profiling_after_fork)
