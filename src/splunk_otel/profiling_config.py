# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import atexit

from opentelemetry.configuration import ConfigurationError
from opentelemetry.configuration._conversion import _dict_to_dataclass
from opentelemetry.configuration._logger_provider import create_logger_provider
from opentelemetry.configuration.file._loader import _validate_schema
from opentelemetry.configuration.models import LoggerProvider as LoggerProviderConfig
from opentelemetry.sdk.resources import Resource

from splunk_otel.profile import (
    _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS,
    _get_profiling_logger,
    ProfilingContext,
)


def configure_continuous_profiling(distribution: dict | None, resource: Resource) -> None:
    config = _mapping(distribution, "distribution")
    for key in ("splunk", "profiling"):
        config = _mapping(config.get(key), key)
    always_on = _mapping(config.get("always_on"), "always_on")
    if "cpu_profiler" not in always_on:
        return

    cpu_profiler = _mapping(always_on["cpu_profiler"], "cpu_profiler")
    interval = cpu_profiler.get("sampling_interval", _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
    if type(interval) is not int or interval <= 0:
        message = "cpu_profiler.sampling_interval must be a positive integer in milliseconds"
        raise ConfigurationError(message)

    logger = _create_profiling_logger(config, resource)
    context = ProfilingContext(resource, interval, logger)
    context.start()
    # The provider registers shutdown first; stop sampling before it flushes at exit.
    atexit.register(context.stop)


def _create_profiling_logger(profiling: dict, resource: Resource):
    exporter = _mapping(profiling.get("exporter"), "profiling.exporter")
    if exporter and set(exporter) != {"otlp_log_http"}:
        message = "profiling.exporter supports only otlp_log_http"
        raise ConfigurationError(message)
    http = _mapping(exporter.get("otlp_log_http"), "profiling.exporter.otlp_log_http")
    http = {"endpoint": "http://localhost:4318/v1/logs", **http}
    provider_config = {"processors": [{"batch": {"exporter": {"otlp_http": http}}}]}
    # Apply the same schema and model conversion as the standard YAML log exporter.
    _validate_schema({"file_format": "1.0", "logger_provider": provider_config})
    provider = create_logger_provider(_dict_to_dataclass(provider_config, LoggerProviderConfig), resource)
    return _get_profiling_logger(provider)


def _mapping(value: object, name: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        message = f"{name} must be a mapping"
        raise ConfigurationError(message)
    return value
