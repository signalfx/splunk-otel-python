# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import atexit
import json
import math
from importlib.resources import files
from urllib.parse import urljoin

from jsonschema import Draft202012Validator, ValidationError, validators
from opentelemetry import trace
from opentelemetry._logs import Logger
from opentelemetry.configuration import ConfigurationError
from opentelemetry.configuration._conversion import _dict_to_dataclass
from opentelemetry.configuration._logger_provider import create_logger_provider
from opentelemetry.configuration._tracer_provider import create_tracer_provider
from opentelemetry.configuration.file._loader import _get_schema
from opentelemetry.configuration.models import LoggerProvider as LoggerProviderConfig
from opentelemetry.exporter.otlp.proto.http import _log_exporter as otlp_http_logs
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor, _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS
from splunk_otel.profile import (
    _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS,
    _get_profiling_logger,
    _start_continuous_profiling,
)
from splunk_otel.propagator import _configure_callgraphs_propagator, _DEFAULT_CALLGRAPHS_SELECTION_PROBABILITY


def _create_profiling_validator():
    profiling_schema = json.loads(files("splunk_otel").joinpath("_profiling_schema.json").read_text(encoding="utf-8"))
    # JSON Schema accepts 1.0 as an integer, but protobuf sampling periods require
    # Python int values. The exact-type check rejects floats and bools for every
    # integer field in this validator, including HTTP exporter settings.
    # YAML also accepts NaN and infinity, which are not JSON numbers.
    type_checker = Draft202012Validator.TYPE_CHECKER.redefine_many(
        {
            "integer": lambda _checker, value: type(value) is int,
            "number": lambda _checker, value: Draft202012Validator.TYPE_CHECKER.is_type(value, "number")
            and (not isinstance(value, float) or math.isfinite(value)),
        }
    )
    validator_class = validators.extend(
        Draft202012Validator,
        type_checker=type_checker,
    )
    opentelemetry_definitions = _get_schema()["$defs"]
    profiling_definitions = profiling_schema["$defs"]
    combined_definitions = {**opentelemetry_definitions, **profiling_definitions}
    combined_schema = {**profiling_schema, "$defs": combined_definitions}
    return validator_class(combined_schema)


_PROFILING_VALIDATOR = _create_profiling_validator()


def _configure_declarative_profiling(distribution_config: dict | None, resource: Resource) -> None:
    _validate_profiling_config(distribution_config)
    profiling_config = _config_at(distribution_config, ("splunk", "profiling"))
    cpu_profiler_config = _profiling_mode_config(profiling_config, ("always_on", "cpu_profiler"))
    callgraphs_config = _profiling_mode_config(profiling_config, ("callgraphs",))
    if cpu_profiler_config is None and callgraphs_config is None:
        return

    if callgraphs_config is not None:
        tracer_provider = _configure_callgraphs_tracer_provider(resource)

    logger_provider = _create_profiling_logger_provider(profiling_config, resource)
    logger = _get_profiling_logger(logger_provider)
    if cpu_profiler_config is not None:
        _configure_declarative_continuous_profiling(cpu_profiler_config, resource=resource, logger=logger)

    if callgraphs_config is not None:
        _configure_declarative_callgraph_profiling(
            callgraphs_config, tracer_provider=tracer_provider, resource=resource, logger=logger
        )


def _configure_callgraphs_tracer_provider(resource: Resource) -> SDKTracerProvider:
    tracer_provider: trace.TracerProvider = trace.get_tracer_provider()
    if isinstance(tracer_provider, SDKTracerProvider):
        return tracer_provider
    if not isinstance(tracer_provider, trace.ProxyTracerProvider):
        message = (
            "distribution.splunk.profiling.callgraphs requires an SDK tracer provider, "
            "but an incompatible global tracer provider is already configured"
        )
        raise ConfigurationError(message)

    tracer_provider = create_tracer_provider(config=None, resource=resource)
    trace.set_tracer_provider(tracer_provider)
    # Another thread can register a provider after the placeholder check.
    if trace.get_tracer_provider() is not tracer_provider:
        tracer_provider.shutdown()
        message = (
            "distribution.splunk.profiling.callgraphs could not install a tracer provider "
            "because a global tracer provider is already configured"
        )
        raise ConfigurationError(message)
    return tracer_provider


def _configure_declarative_continuous_profiling(
    cpu_profiler_config: dict, *, resource: Resource, logger: Logger
) -> None:
    interval_millis = cpu_profiler_config.get("sampling_interval", _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)
    _start_continuous_profiling(resource=resource, interval_millis=interval_millis, logger=logger)


def _configure_declarative_callgraph_profiling(
    callgraphs_config: dict, *, tracer_provider: SDKTracerProvider, resource: Resource, logger: Logger
) -> None:
    processor = CallgraphsSpanProcessor(
        resource=resource,
        logger=logger,
        sampling_interval=callgraphs_config.get("sampling_interval", _DEFAULT_CALLGRAPHS_SAMPLING_INTERVAL_MILLIS),
    )
    tracer_provider.add_span_processor(processor)
    # Stop sampling before the profiling exporter flushes at exit.
    atexit.register(processor.shutdown)
    _configure_callgraphs_propagator(
        callgraphs_config.get("selection_probability", _DEFAULT_CALLGRAPHS_SELECTION_PROBABILITY)
    )


def _create_profiling_logger_provider(profiling_config: dict, resource: Resource) -> LoggerProvider:
    http_exporter_config = _config_at(profiling_config, ("exporter", "otlp_log_http"))
    default_endpoint = urljoin(otlp_http_logs.DEFAULT_ENDPOINT, otlp_http_logs.DEFAULT_LOGS_EXPORT_PATH)
    # Missing or null endpoints must use the SDK default rather than environment settings.
    endpoint = http_exporter_config.get("endpoint") or default_endpoint
    http_exporter_config = {**http_exporter_config, "endpoint": endpoint}
    logger_provider_data = {"processors": [{"batch": {"exporter": {"otlp_http": http_exporter_config}}}]}
    logger_provider_config = _dict_to_dataclass(logger_provider_data, LoggerProviderConfig)
    return create_logger_provider(logger_provider_config, resource)


def _config_at(config: dict | None, path: tuple[str, ...]) -> dict:
    """Read mapping-valued sections from already validated configuration."""
    section = config or {}
    for key in path:
        section = section.get(key) or {}
    return section


def _profiling_mode_config(profiling_config: dict, path: tuple[str, ...]) -> dict | None:
    """Absent modes are disabled; null or empty mode blocks enable defaults."""
    parent_config = _config_at(profiling_config, path[:-1])
    mode_key = path[-1]
    if mode_key not in parent_config:
        return None
    return parent_config[mode_key] or {}


def _validate_profiling_config(distribution_config: dict | None) -> None:
    try:
        _PROFILING_VALIDATOR.validate(distribution_config)
    except ValidationError as error:
        config_path = ".".join(["distribution", *(str(part) for part in error.absolute_path)])
        message = f"{config_path}: {error.message}"
        raise ConfigurationError(message) from error
