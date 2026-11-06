# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.configuration import ConfigurationError
from opentelemetry.configuration._conversion import _dict_to_dataclass
from opentelemetry.configuration._logger_provider import create_logger_provider
from opentelemetry.configuration.file._loader import _validate_schema
from opentelemetry.configuration.models import LoggerProvider as LoggerProviderConfig
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.resources import Resource

from splunk_otel.profile import (
    _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS,
    _get_profiling_logger,
    _start_continuous_profiling,
)


def _configure_declarative_continuous_profiling(distribution: dict | None, resource: Resource) -> None:
    distribution = _mapping_or_empty(distribution, "distribution")
    splunk = _mapping_or_empty(distribution.get("splunk"), "splunk")
    profiling = _mapping_or_empty(splunk.get("profiling"), "profiling")
    always_on = _mapping_or_empty(profiling.get("always_on"), "always_on")
    if "cpu_profiler" not in always_on:
        return

    cpu_profiler = _mapping_or_empty(always_on["cpu_profiler"], "cpu_profiler")
    interval_millis = cpu_profiler.get("sampling_interval", _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
    if type(interval_millis) is not int or interval_millis <= 0:
        message = "cpu_profiler.sampling_interval must be a positive integer in milliseconds"
        raise ConfigurationError(message)

    logger_provider = _create_profiling_logger_provider(profiling, resource)
    logger = _get_profiling_logger(logger_provider)
    _start_continuous_profiling(resource=resource, interval_millis=interval_millis, logger=logger)


def _create_profiling_logger_provider(profiling: dict, resource: Resource) -> LoggerProvider:
    exporter = _mapping_or_empty(profiling.get("exporter"), "profiling.exporter")
    if exporter and set(exporter) != {"otlp_log_http"}:
        message = "profiling.exporter supports only otlp_log_http"
        raise ConfigurationError(message)
    http_exporter_config = _mapping_or_empty(exporter.get("otlp_log_http"), "profiling.exporter.otlp_log_http")
    http_exporter_config = {"endpoint": "http://localhost:4318/v1/logs", **http_exporter_config}
    logger_provider_data = {"processors": [{"batch": {"exporter": {"otlp_http": http_exporter_config}}}]}
    # Apply the same schema and model conversion as the standard YAML log exporter.
    _validate_schema({"file_format": "1.0", "logger_provider": logger_provider_data})
    logger_provider_config = _dict_to_dataclass(logger_provider_data, LoggerProviderConfig)
    return create_logger_provider(logger_provider_config, resource)


def _mapping_or_empty(value: object, name: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        message = f"{name} must be a mapping"
        raise ConfigurationError(message)
    return value
