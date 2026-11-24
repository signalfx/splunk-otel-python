# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import logging

from opentelemetry import trace
from opentelemetry.instrumentation.version import __version__ as version
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import Resource

from splunk_otel._logging import log_exception
from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor, _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS
from splunk_otel.env import (
    Env,
    SPLUNK_PROFILER_ENABLED,
    SPLUNK_PROFILER_CALL_STACK_INTERVAL,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
)
from splunk_otel.profile import (
    ProfilingContext,
    _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS,
    _get_profiling_logger,
    _start_continuous_profiling,
)


_logger = logging.getLogger(__name__)


def configure_environment_profiling(env: Env | None = None) -> None:
    env = env or Env()
    if env.is_true(SPLUNK_PROFILER_ENABLED):
        start_continuous_profiling_from_env(env)
    if env.is_true(SPLUNK_SNAPSHOT_PROFILER_ENABLED):
        start_snapshot_profiling_from_env(env)


def start_continuous_profiling_from_env(env: Env | None = None) -> ProfilingContext | None:
    try:
        env = env or Env()
        interval_millis = env.getint(SPLUNK_PROFILER_CALL_STACK_INTERVAL, _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
        return _start_continuous_profiling(
            resource=_mk_resource(env.getval(OTEL_SERVICE_NAME)),
            interval_millis=interval_millis,
            logger=_get_profiling_logger(),
        )
    except Exception:  # noqa: BLE001
        log_exception(_logger, "Failed to configure continuous profiling from environment settings")
        return None


def start_snapshot_profiling_from_env(env: Env) -> None:
    try:
        trace.get_tracer_provider().add_span_processor(
            CallgraphsSpanProcessor(
                _mk_resource(env.getval(OTEL_SERVICE_NAME)),
                _get_profiling_logger(),
                env.getint(SPLUNK_SNAPSHOT_SAMPLING_INTERVAL, _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS),
            )
        )
    except Exception:  # noqa: BLE001
        log_exception(_logger, "Failed to configure snapshot profiling from environment settings")


def _mk_resource(service_name: str) -> Resource:
    return Resource.create(
        {
            "splunk.distro.version": version,
            "service.name": service_name,
        }
    )
