# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

import json
from importlib.resources import files

from jsonschema import Draft202012Validator, ValidationError, validators
from opentelemetry.configuration import ConfigurationError
from opentelemetry.configuration._conversion import _dict_to_dataclass
from opentelemetry.configuration._logger_provider import create_logger_provider
from opentelemetry.configuration.file._loader import _get_schema
from opentelemetry.configuration.models import LoggerProvider as LoggerProviderConfig
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.resources import Resource

from splunk_otel.profile import (
    _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS,
    _get_profiling_logger,
    _start_continuous_profiling,
)


def _create_profiling_validator():
    profiling_schema = json.loads(files("splunk_otel").joinpath("_profiling_schema.json").read_text(encoding="utf-8"))
    # JSON Schema accepts 1.0 as an integer, but protobuf sampling periods require
    # Python int values. The exact-type check rejects floats and bools for every
    # integer field in this validator, including HTTP exporter settings.
    validator_class = validators.extend(
        Draft202012Validator,
        type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _checker, value: type(value) is int),
    )
    opentelemetry_definitions = _get_schema()["$defs"]
    profiling_definitions = profiling_schema["$defs"]
    combined_definitions = {**opentelemetry_definitions, **profiling_definitions}
    combined_schema = {**profiling_schema, "$defs": combined_definitions}
    return validator_class(combined_schema)


_PROFILING_VALIDATOR = _create_profiling_validator()


def _configure_declarative_continuous_profiling(distribution: dict | None, resource: Resource) -> None:
    _validate_profiling_config(distribution)
    splunk = (distribution or {}).get("splunk") or {}
    profiling = splunk.get("profiling") or {}
    always_on = profiling.get("always_on") or {}
    if "cpu_profiler" not in always_on:
        return

    cpu_profiler = always_on["cpu_profiler"] or {}
    interval_millis = cpu_profiler.get("sampling_interval", _DEFAULT_PROF_CALL_STACK_INTERVAL_MILLIS)

    logger_provider = _create_profiling_logger_provider(profiling, resource)
    logger = _get_profiling_logger(logger_provider)
    _start_continuous_profiling(resource=resource, interval_millis=interval_millis, logger=logger)


def _create_profiling_logger_provider(profiling: dict, resource: Resource) -> LoggerProvider:
    exporter = profiling.get("exporter") or {}
    http_exporter_config = exporter.get("otlp_log_http") or {}
    http_exporter_config = {"endpoint": "http://localhost:4318/v1/logs", **http_exporter_config}
    logger_provider_data = {"processors": [{"batch": {"exporter": {"otlp_http": http_exporter_config}}}]}
    logger_provider_config = _dict_to_dataclass(logger_provider_data, LoggerProviderConfig)
    return create_logger_provider(logger_provider_config, resource)


def _validate_profiling_config(distribution: dict | None) -> None:
    try:
        _PROFILING_VALIDATOR.validate(distribution)
    except ValidationError as error:
        path = ".".join(["distribution", *(str(part) for part in error.absolute_path)])
        message = f"{path}: {error.message}"
        raise ConfigurationError(message) from error
