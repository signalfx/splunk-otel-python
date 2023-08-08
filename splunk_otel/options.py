# Copyright Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from os import environ
from typing import Callable, Collection, Dict, List, Optional, Tuple, Union

from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.instrumentation.propagators import ResponsePropagator
from opentelemetry.instrumentation.version import (
    __version__ as auto_instrumentation_version,
)
from opentelemetry.sdk.environment_variables import (
    OTEL_ATTRIBUTE_COUNT_LIMIT,
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
    OTEL_EXPORTER_JAEGER_ENDPOINT,
    OTEL_LINK_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_EVENT_COUNT_LIMIT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SpanExporter
from pkg_resources import iter_entry_points

from splunk_otel.env import _EnvVarsABC, _OSEnvVars
from splunk_otel.environment_variables import (
    _SPLUNK_ACCESS_TOKEN,
    _SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
)
from splunk_otel.propagators import _ServerTimingResponsePropagator
from splunk_otel.symbols import (
    _DEFAULT_EXPORTERS,
    _DEFAULT_JAEGER_ENDPOINT,
    _DEFAULT_MAX_ATTR_LENGTH,
    _DEFAULT_OTEL_SERVICE_NAME,
    _DEFAULT_SERVICE_NAME,
    _DEFAULT_SPAN_LINK_COUNT_LIMIT,
    _EXPORTER_JAEGER_SPLUNK,
    _EXPORTER_JAEGER_THRIFT,
    _EXPORTER_OTLP,
    _EXPORTER_OTLP_GRPC,
    _KNOWN_EXPORTER_PACKAGES,
    _LIMIT_UNSET_VALUE,
    _NO_SERVICE_NAME_WARNING,
    _SERVICE_NAME_ATTR,
    _SPLUNK_DISTRO_VERSION_ATTR,
    _TELEMETRY_VERSION_ATTR,
)
from splunk_otel.version import __version__

_SpanExporterFactory = Callable[["_Options"], SpanExporter]
_SpanExporterClass = Callable[..., SpanExporter]

logger = logging.getLogger("options")


class _Options:
    span_exporter_factories: Collection[_SpanExporterFactory]
    access_token: Optional[str]
    resource: Resource
    response_propagation: bool
    response_propagator: Optional[ResponsePropagator]

    def __init__(
        self,
        service_name: Optional[str] = None,
        span_exporter_factories: Optional[Collection[_SpanExporterFactory]] = None,
        access_token: Optional[str] = None,
        resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
        trace_response_header_enabled: Optional[bool] = None,
        env: Optional[_EnvVarsABC] = _OSEnvVars(),
    ):
        self._set_default_env(env)
        self.access_token = self._get_access_token(env, access_token)
        self.response_propagator = self._get_response_propagator(env, trace_response_header_enabled)
        self.resource = self._get_resource(service_name, resource_attributes)
        self.span_exporter_factories = self._get_span_exporter_factories(
            env,
            span_exporter_factories
        )

    @staticmethod
    def _get_access_token(env: _EnvVarsABC, access_token: Optional[str]) -> Optional[str]:
        if not access_token:
            access_token = env._get(_SPLUNK_ACCESS_TOKEN)
        return access_token or None

    @staticmethod
    def _get_response_propagator(
        env: _EnvVarsABC,
        enabled: Optional[bool],
    ) -> Optional[ResponsePropagator]:
        if enabled is None:
            enabled = _Options._is_truthy(env._get(_SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, "true"))
        if enabled:
            return _ServerTimingResponsePropagator()
        return None

    @staticmethod
    def _get_resource(
        service_name: Optional[str],
        attributes: Optional[Dict[str, Union[str, bool, int, float]]],
    ) -> Resource:
        attributes = attributes or {}
        if service_name:
            attributes[_SERVICE_NAME_ATTR] = service_name
        attributes.update(
            {
                _TELEMETRY_VERSION_ATTR: auto_instrumentation_version,
                _SPLUNK_DISTRO_VERSION_ATTR: __version__,
            }
        )
        resource = Resource.create(attributes)
        if (
            resource.attributes.get(_SERVICE_NAME_ATTR, _DEFAULT_OTEL_SERVICE_NAME)
            == _DEFAULT_OTEL_SERVICE_NAME
        ):
            logger.warning(_NO_SERVICE_NAME_WARNING)
            resource = resource.merge(
                Resource({_SERVICE_NAME_ATTR: _DEFAULT_SERVICE_NAME})
            )
        return resource

    @staticmethod
    def _get_span_exporter_factories(
        env: _EnvVarsABC,
        factories: Optional[Collection[_SpanExporterFactory]],
    ) -> Collection[_SpanExporterFactory]:
        if factories:
            return factories

        exporter_names = _Options._get_span_exporter_names_from_env(env)
        return _Options._import_span_exporter_factories(exporter_names)

    @classmethod
    def _is_truthy(cls, value: Optional[str]) -> bool:
        if not value:
            return False

        return value.strip().lower() not in (
            "false",
            "no",
            "f",
            "0",
        )

    @staticmethod
    def _set_default_env(env: Optional[_EnvVarsABC] = _OSEnvVars()) -> None:
        defaults = {
            OTEL_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
            OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
            OTEL_SPAN_EVENT_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
            OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
            OTEL_LINK_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
            OTEL_SPAN_LINK_COUNT_LIMIT: str(_DEFAULT_SPAN_LINK_COUNT_LIMIT),
            OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: str(_DEFAULT_MAX_ATTR_LENGTH),
        }
        env._set_all_unset(defaults)

    @classmethod
    def _get_span_exporter_names_from_env(cls, env: _EnvVarsABC) -> Collection[Tuple[str, str]]:
        exporters_env = (
            env._get(OTEL_TRACES_EXPORTER, "").strip() or _DEFAULT_EXPORTERS
        )

        exporters: List[Tuple[str, str]] = []
        if not cls._is_truthy(exporters_env):
            return exporters

        # exporters are known by different names internally by Python Otel SDK.
        # Here we create a mapping of user provided names to internal names so
        # that we can provide helpful error messages later.
        for name in exporters_env.split(","):
            if name == _EXPORTER_OTLP:
                exporters.append((_EXPORTER_OTLP, _EXPORTER_OTLP_GRPC))
            elif name == _EXPORTER_JAEGER_SPLUNK:
                exporters.append((_EXPORTER_JAEGER_SPLUNK, _EXPORTER_JAEGER_THRIFT))
            else:
                exporters.append(
                    (
                        name,
                        name,
                    )
                )
        return exporters

    @staticmethod
    def _import_span_exporter_factories(
        requested_exporter_names: Collection[Tuple[str, str]],
    ) -> Collection[_SpanExporterFactory]:
        factories = []
        entry_points = {
            ep.name: ep for ep in iter_entry_points("opentelemetry_traces_exporter")
        }

        for name, internal_name in requested_exporter_names:
            if internal_name not in entry_points:
                package = _KNOWN_EXPORTER_PACKAGES.get(internal_name)
                if package:
                    help_msg = f"please make sure {package} is installed"
                else:
                    help_msg = (
                        "please make sure the relevant exporter package is installed."
                    )
                raise ValueError(
                    f'exporter "{name} ({internal_name})" not found. {help_msg}'
                )

            exporter_class: _SpanExporterClass = entry_points[internal_name].load()
            if name == _EXPORTER_JAEGER_SPLUNK:
                factory = _Options._mk_splunk_jaeger_factory(exporter_class)
            elif internal_name == _EXPORTER_JAEGER_THRIFT:
                factory = _Options._mk_jaeger_factory(exporter_class)
            elif internal_name == _EXPORTER_OTLP_GRPC:
                factory = _Options._mk_otlp_factory(exporter_class)
            else:
                factory = _Options._mk_generic_exporter(exporter_class)
            factories.append(factory)
        return factories

    @staticmethod
    def _mk_splunk_jaeger_factory(exporter: _SpanExporterClass):
        def f(options: "_Options"):
            kwargs = _Options._get_jaeger_kwargs(options)
            endpt = environ.get(OTEL_EXPORTER_JAEGER_ENDPOINT, _DEFAULT_JAEGER_ENDPOINT)
            kwargs.update({"collector_endpoint": endpt})
            return exporter(**kwargs)

        return f

    @staticmethod
    def _mk_jaeger_factory(exporter: _SpanExporterClass):
        return lambda options: exporter(**_Options._get_jaeger_kwargs(options))

    @staticmethod
    def _mk_otlp_factory(exporter: _SpanExporterClass):
        return lambda options: exporter(headers=(("x-sf-token", options.access_token),))

    @staticmethod
    def _mk_generic_exporter(exporter: _SpanExporterClass):
        return lambda options: exporter()

    @staticmethod
    def _get_jaeger_kwargs(options: "_Options") -> Dict[str, str]:
        if options.access_token:
            return {
                "username": "auth",
                "password": options.access_token,
            }
        return {}
