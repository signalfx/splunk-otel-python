# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import ClassVar

import pytest


@pytest.fixture
def profiling_timer_type(monkeypatch):
    class FakeProfilingTimer:
        instances: ClassVar[list["FakeProfilingTimer"]] = []
        fail_start = False
        fail_pause = False

        def __init__(self, _interval_millis, _target):
            self.pause_count = 0
            self.instances.append(self)

        def start(self):
            if self.fail_start:
                message = "timer start failed"
                raise RuntimeError(message)
            return True

        def stop(self):
            pass

        def pause_after(self, _seconds):
            self.pause_count += 1
            if self.fail_pause:
                message = "timer pause failed"
                raise RuntimeError(message)

    monkeypatch.setattr("splunk_otel.profile._IntervalTimer", FakeProfilingTimer)
    return FakeProfilingTimer


@pytest.fixture
def failed_profiler_diagnostics(caplog, monkeypatch, tmp_path):
    handler = logging.FileHandler(tmp_path / "missing" / "profiler.log", delay=True)
    for name in ("splunk_otel.profile", "splunk_otel.callgraphs.span_processor"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "handlers", [caplog.handler, handler])
        monkeypatch.setattr(logger, "propagate", False)
    yield
    handler.close()
