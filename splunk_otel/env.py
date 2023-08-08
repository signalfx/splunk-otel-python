from abc import ABC, abstractmethod
from os import environ
from typing import Optional, Dict

from opentelemetry.sdk.environment_variables import (
    OTEL_ATTRIBUTE_COUNT_LIMIT,
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
    OTEL_LINK_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_EVENT_COUNT_LIMIT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
)

from splunk_otel.symbols import (
    _DEFAULT_MAX_ATTR_LENGTH,
    _DEFAULT_SPAN_LINK_COUNT_LIMIT,
    _LIMIT_UNSET_VALUE,
)


class _EnvVarsABC(ABC):

    @abstractmethod
    def _get(self, k: str, default: Optional[any] = None):
        pass

    @abstractmethod
    def _set(self, k: str, v: str):
        pass

    @abstractmethod
    def _set_all_unset(self, pairs: Dict):
        pass


class _OSEnvVars(_EnvVarsABC):

    def _get(self, k, default: Optional[any] = None):
        # todo check if explicit None is ok
        return environ.get(k, default)

    def _set(self, k, v):
        environ[k] = v

    def _set_all_unset(self, pairs: Dict):
        for k, v in pairs.items():
            if k not in environ:
                environ[k] = v


class _FakeEnvVars(_EnvVarsABC):

    def __init__(self, starting_env=None):
        self._env = starting_env or {}
        self._written = {}
        self._read = []

    def _get(self, k: str, default: Optional[any] = None) -> any:
        self._read.append(k)
        out = self._env.get(k)
        return default if out is None else out

    def _set_all_unset(self, pairs: Dict):
        for k, v in pairs.items():
            if k not in self._written:
                self._set(k, v)

    def _set(self, k: str, v: str):
        self._written[k] = v
        self._env[v] = v

    def _get_env_vars_written(self):
        return self._written

    def _get_env_vars_read(self):
        return self._read

def _set_default_env(env: _EnvVarsABC) -> None:
    env._set_all_unset({
        OTEL_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_SPAN_EVENT_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_LINK_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_SPAN_LINK_COUNT_LIMIT: str(_DEFAULT_SPAN_LINK_COUNT_LIMIT),
        OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: str(_DEFAULT_MAX_ATTR_LENGTH),
    })
