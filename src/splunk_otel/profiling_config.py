# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.configuration import ConfigurationError
from opentelemetry.sdk.resources import Resource

from splunk_otel.profile import (
    _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS,
    _get_profiling_logger,
    ProfilingContext,
)


def configure_continuous_profiling(distribution: dict | None, resource: Resource) -> None:
    config = _mapping(distribution, "distribution")
    for key in ("splunk", "profiling", "always_on"):
        config = _mapping(config.get(key), key)
    if "cpu_profiler" not in config:
        return

    cpu_profiler = _mapping(config["cpu_profiler"], "cpu_profiler")
    interval = cpu_profiler.get("sampling_interval", _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
    if type(interval) is not int or interval <= 0:
        message = "cpu_profiler.sampling_interval must be a positive integer in milliseconds"
        raise ConfigurationError(message)

    context = ProfilingContext(resource, interval, _get_profiling_logger())
    context.start()


def _mapping(value: object, name: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        message = f"{name} must be a mapping"
        raise ConfigurationError(message)
    return value
