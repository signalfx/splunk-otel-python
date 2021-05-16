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
from functools import partial
from os import environ
from typing import Callable, Collection, Dict, List, Optional, Tuple, Union

from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.instrumentation.propagators import ResponsePropagator
from opentelemetry.instrumentation.version import (
    __version__ as auto_instrumentation_version,
)
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_JAEGER_ENDPOINT,
    OTEL_SERVICE_NAME,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SpanExporter
from pkg_resources import iter_entry_points

from splunk_otel.environment_variables import (
    SPLUNK_ACCESS_TOKEN,
    SPLUNK_MAX_ATTR_LENGTH,
    SPLUNK_SERVICE_NAME,
    SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
)
from splunk_otel.propagators import ServerTimingResponsePropagator
from splunk_otel.symbols import (
    _DEFAULT_EXPORTERS,
    _DEFAULT_JAEGER_ENDPOINT,
    _DEFAULT_MAX_ATTR_LENGTH,
    _DEFAULT_OTEL_SERVICE_NAME,
    _DEFAULT_SERVICE_NAME,
    _EXPORTER_JAEGER_SPLUNK,
    _EXPORTER_JAEGER_THRIFT,
    _EXPORTER_OTLP,
    _EXPORTER_OTLP_GRPC,
    _KNOWN_EXPORTER_PACKAGES,
    _NO_SERVICE_NAME_WARNING,
    _SERVICE_NAME_ATTR,
    _SPLUNK_DISTRO_VERSION_ATTR,
    _TELEMETRY_VERSION_ATTR,
)
from splunk_otel.version import __version__

_SpanExporterFactory = Callable[["Options"], SpanExporter]
_SpanExporterClass = Callable[..., SpanExporter]

logger = logging.getLogger("options")


class Options:
    span_exporter_factories: Collection[_SpanExporterFactory]
    access_token: Optional[str]
    max_attr_length: int
    resource: Resource
    response_propagation: bool
    response_propagator: Optional[ResponsePropagator]

    def __init__(
        self,
        service_name: Optional[str] = None,
        span_exporter_factories: Optional[Collection[_SpanExporterFactory]] = None,
        access_token: Optional[str] = None,
        max_attr_length: Optional[int] = None,
        resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
        trace_response_header_enabled: Optional[bool] = None,
    ):
        self._set_default_env()
        self.access_token = self._get_access_token(access_token)
        self.max_attr_length = self._get_max_attr_length(max_attr_length)
        self.response_propagator = self._get_trace_response_header_enabled(
            trace_response_header_enabled
        )
        self.resource = self._get_resource(service_name, resource_attributes)
        self.span_exporter_factories = self._get_span_exporter_factories(
            span_exporter_factories
        )

    @staticmethod
    def _get_access_token(access_token: Optional[str]) -> Optional[str]:
        if not access_token:
            access_token = environ.get(SPLUNK_ACCESS_TOKEN)
        return access_token or None

    @staticmethod
    def _get_max_attr_length(max_attr_length: Optional[int]) -> int:
        if not max_attr_length:
            value = environ.get(SPLUNK_MAX_ATTR_LENGTH)
            if value:
                try:
                    max_attr_length = int(value)
                except (TypeError, ValueError):
                    logger.error("SPLUNK_MAX_ATTR_LENGTH must be a number.")
        return max_attr_length or _DEFAULT_MAX_ATTR_LENGTH

    @staticmethod
    def _get_trace_response_header_enabled(
        enabled: Optional[bool],
    ) -> Optional[ResponsePropagator]:
        if enabled is None:
            enabled = Options._is_truthy(
                environ.get(SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, "true")
            )
        if enabled:
            return ServerTimingResponsePropagator()
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
        factories: Optional[Collection[_SpanExporterFactory]],
    ) -> Collection[_SpanExporterFactory]:
        if factories:
            return factories

        exporter_names = Options._get_span_exporter_names_from_env()
        return Options._import_span_exporter_factories(exporter_names)

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
    def _set_default_env() -> None:
        otel_service_name = environ.get(OTEL_SERVICE_NAME, "")
        splunk_service_name = environ.get(SPLUNK_SERVICE_NAME)
        if not otel_service_name and splunk_service_name:
            logger.warning(
                "SPLUNK_SERVICE_NAME is deprecated and will be removed soon. Please use OTEL_SERVICE_NAME instead"
            )
            environ[OTEL_SERVICE_NAME] = splunk_service_name

    @classmethod
    def _get_span_exporter_names_from_env(cls) -> Collection[Tuple[str, str]]:
        exporters_env = (
            environ.get(OTEL_TRACES_EXPORTER, "").strip() or _DEFAULT_EXPORTERS
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
        exporter_names: Collection[Tuple[str, str]],
    ) -> Collection[_SpanExporterFactory]:
        factories = []
        entry_points = {ep.name: ep for ep in iter_entry_points("opentelemetry_exporter")}

        for name, internal_name in exporter_names:
            if internal_name not in entry_points:
                package = _KNOWN_EXPORTER_PACKAGES.get(internal_name)
                if package:
                    help_msg = "please make sure {0} is installed".format(package)
                else:
                    help_msg = (
                        "please make sure the relevant exporter package is installed."
                    )
                raise ValueError(
                    'exporter "{0} ({1})" not found. {2}'.format(
                        name, internal_name, help_msg
                    )
                )

            exporter_class: _SpanExporterClass = entry_points[internal_name].load()
            if name == _EXPORTER_JAEGER_SPLUNK:
                factory = Options._splunk_jaeger_factory
            elif internal_name == _EXPORTER_JAEGER_THRIFT:
                factory = Options._jaeger_factory
            elif internal_name == _EXPORTER_OTLP_GRPC:
                factory = Options._otlp_factory
            else:
                factory = Options._generic_exporter
            factories.append(partial(factory, exporter_class))
        return factories

    @staticmethod
    def _generic_exporter(
        exporter: _SpanExporterClass,
        options: "Options",  # pylint: disable=unused-argument
    ) -> SpanExporter:
        return exporter()

    @staticmethod
    def _splunk_jaeger_factory(
        exporter: _SpanExporterClass, options: "Options"
    ) -> SpanExporter:
        kwargs = Options._get_jaeger_kwargs(options)
        kwargs.update(
            {
                "collector_endpoint": environ.get(
                    OTEL_EXPORTER_JAEGER_ENDPOINT, _DEFAULT_JAEGER_ENDPOINT
                ),
            }
        )
        return exporter(**kwargs)

    @staticmethod
    def _jaeger_factory(exporter: _SpanExporterClass, options: "Options") -> SpanExporter:
        return exporter(**Options._get_jaeger_kwargs(options))

    @staticmethod
    def _get_jaeger_kwargs(options: "Options") -> Dict[str, Union[int, str]]:
        kwargs: Dict[str, Union[int, str]] = {
            "max_tag_value_length": options.max_attr_length,
        }
        if options.access_token:
            kwargs.update(
                {
                    "username": "auth",
                    "password": options.access_token,
                }
            )
        return kwargs

    @staticmethod
    def _otlp_factory(exporter: _SpanExporterClass, options: "Options") -> SpanExporter:
        # TODO: enable after PR is merged and released:
        # https://github.com/open-telemetry/opentelemetry-python/pull/1824
        # kwargs = {"max_attr_value_length": self.max_attr_length}
        return exporter(headers=(("x-sf-token", options.access_token),))
