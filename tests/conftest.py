# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import ClassVar

import pytest


@pytest.fixture
def profiling_timer_type(monkeypatch):
    class FakeProfilingTimer:
        instances: ClassVar[list["FakeProfilingTimer"]] = []
        fail_construction = False
        fail_start = False
        fail_stop = False
        fail_pause = False

        def __init__(self, interval_millis, target):
            if self.fail_construction:
                message = "timer construction failed"
                raise RuntimeError(message)
            self.interval_millis = interval_millis
            self.target = target
            self.started = False
            self.stopped = False
            self.stop_count = 0
            self.pause_count = 0
            self.instances.append(self)

        def start(self):
            if self.fail_start:
                message = "timer start failed"
                raise RuntimeError(message)
            self.started = True
            return True

        def is_current_process(self):
            return True

        def stop(self):
            if self.fail_stop:
                message = "timer stop failed"
                raise RuntimeError(message)
            self.started = False
            self.stopped = True
            self.stop_count += 1

        def pause_after(self, _seconds):
            self.pause_count += 1
            if self.fail_pause:
                message = "timer pause failed"
                raise RuntimeError(message)

    monkeypatch.setattr("splunk_otel.profile._IntervalTimer", FakeProfilingTimer)
    return FakeProfilingTimer


@pytest.fixture
def failed_profiler_diagnostics(monkeypatch, tmp_path):
    handler = logging.FileHandler(tmp_path / "missing" / "profiler.log", delay=True)
    for name in (
        "splunk_otel.profile",
        "splunk_otel.callgraphs.span_processor",
        "splunk_otel._environment_profiling",
        "splunk_otel._declarative_profiling",
    ):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "handlers", [handler])
        monkeypatch.setattr(logger, "propagate", False)
    yield
    handler.close()
