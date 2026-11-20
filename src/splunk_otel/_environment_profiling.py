# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import TYPE_CHECKING, cast

from opentelemetry import trace
from opentelemetry.instrumentation.version import __version__ as version
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import Resource

from splunk_otel import _profiling
from splunk_otel.callgraphs.span_processor import _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS
from splunk_otel.env import (
    Env,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
    SPLUNK_SNAPSHOT_SELECTION_PROBABILITY,
)
from splunk_otel.profile import ProfilingContext, _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS, _get_profiling_logger
from splunk_otel.propagator import _DEFAULT_CALLGRAPHS_SELECTION_PROBABILITY

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

_logger = logging.getLogger(__name__)


def _configure_environment_profiling(env: Env | None = None) -> None:
    env = env or Env()
    if env.is_true(SPLUNK_PROFILER_ENABLED):
        _start_continuous_profiling_from_env(env)
    if env.is_true(SPLUNK_SNAPSHOT_PROFILER_ENABLED):
        _start_snapshot_profiling_from_env(env)


def _start_continuous_profiling_from_env(env: Env | None = None) -> ProfilingContext | None:
    try:
        env = env or Env()
        interval_millis = env.getint(SPLUNK_PROFILER_CALL_STACK_INTERVAL, _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
        return _profiling.profiling_controller.start_continuous(
            resource=_mk_resource(env.getval(OTEL_SERVICE_NAME)),
            sampling_interval=interval_millis,
            logger=_get_profiling_logger(),
        )
    except Exception:
        _logger.exception("Failed to configure continuous profiling from environment settings")
        return None


def _start_snapshot_profiling_from_env(env: Env) -> None:
    try:
        sampling_interval = env.getint(SPLUNK_SNAPSHOT_SAMPLING_INTERVAL, _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS)
        selection_probability = env.getfloat(
            SPLUNK_SNAPSHOT_SELECTION_PROBABILITY, _DEFAULT_CALLGRAPHS_SELECTION_PROBABILITY
        )
        _profiling.profiling_controller.start_snapshot(
            tracer_provider=cast("TracerProvider", trace.get_tracer_provider()),
            resource=_mk_resource(env.getval(OTEL_SERVICE_NAME)),
            logger=_get_profiling_logger(),
            sampling_interval=sampling_interval,
            selection_probability=selection_probability,
        )
    except Exception:
        _logger.exception("Failed to configure snapshot profiling from environment settings")


def _mk_resource(service_name: str) -> Resource:
    return Resource.create(
        {
            "splunk.distro.version": version,
            "service.name": service_name,
        }
    )
