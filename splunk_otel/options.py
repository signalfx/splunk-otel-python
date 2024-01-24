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
    OTEL_ATTRIBUTE_COUNT_LIMIT,
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
    OTEL_LINK_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_EVENT_COUNT_LIMIT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SpanExporter
from pkg_resources import iter_entry_points

from splunk_otel.environment_variables import (
    _SPLUNK_ACCESS_TOKEN,
    _SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
)
from splunk_otel.propagators import _ServerTimingResponsePropagator
from splunk_otel.symbols import (
    _DEFAULT_EXPORTERS,
    _DEFAULT_MAX_ATTR_LENGTH,
    _DEFAULT_OTEL_SERVICE_NAME,
    _DEFAULT_SERVICE_NAME,
    _DEFAULT_SPAN_LINK_COUNT_LIMIT,
    _EXPORTER_OTLP,
    _EXPORTER_OTLP_GRPC,
    _KNOWN_EXPORTER_PACKAGES,
    _LIMIT_UNSET_VALUE,
    _NO_SERVICE_NAME_WARNING,
    _SERVICE_NAME_ATTR,
    _SPLUNK_DISTRO_VERSION_ATTR,
    _TELEMETRY_VERSION_ATTR,
)
from splunk_otel.util import _is_truthy_str
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
    ):
        # todo: remove this side effect
        _set_default_env()

        self.access_token = _resolve_access_token(access_token)
        self.response_propagator = _get_response_propagator(trace_response_header_enabled)
        self.resource = _create_resource(service_name, resource_attributes)
        self.span_exporter_factories = _get_span_exporter_factories(
            span_exporter_factories
        )


def _resolve_access_token(access_token: Optional[str]) -> Optional[str]:
    if not access_token:
        access_token = environ.get(_SPLUNK_ACCESS_TOKEN)
    return access_token or None


def _get_response_propagator(
    enabled: Optional[bool],
) -> Optional[ResponsePropagator]:
    if enabled is None:
        enabled = _is_truthy_str(
            environ.get(_SPLUNK_TRACE_RESPONSE_HEADER_ENABLED, "true")
        )
    if enabled:
        return _ServerTimingResponsePropagator()
    return None


def _create_resource(
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
        resource = resource.merge(Resource({_SERVICE_NAME_ATTR: _DEFAULT_SERVICE_NAME}))
    return resource


def _get_span_exporter_factories(
    factories: Optional[Collection[_SpanExporterFactory]],
) -> Collection[_SpanExporterFactory]:
    if factories:
        return factories

    exporter_names = _get_span_exporter_names_from_env()
    return _import_span_exporter_factories(exporter_names)


def _set_default_env() -> None:
    defaults = {
        OTEL_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_SPAN_EVENT_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_LINK_ATTRIBUTE_COUNT_LIMIT: _LIMIT_UNSET_VALUE,
        OTEL_SPAN_LINK_COUNT_LIMIT: str(_DEFAULT_SPAN_LINK_COUNT_LIMIT),
        OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: str(_DEFAULT_MAX_ATTR_LENGTH),
    }

    for key, value in defaults.items():
        if key not in environ:
            environ[key] = value


def _get_span_exporter_names_from_env() -> Collection[Tuple[str, str]]:
    exporters_env = environ.get(OTEL_TRACES_EXPORTER, "").strip() or _DEFAULT_EXPORTERS

    exporters: List[Tuple[str, str]] = []
    if not _is_truthy_str(exporters_env):
        return exporters

    # exporters are known by different names internally by Python Otel SDK.
    # Here we create a mapping of user provided names to internal names so
    # that we can provide helpful error messages later.
    for name in exporters_env.split(","):
        if name == _EXPORTER_OTLP:
            exporters.append((_EXPORTER_OTLP, _EXPORTER_OTLP_GRPC))
        else:
            exporters.append(
                (
                    name,
                    name,
                )
            )
    return exporters


def _import_span_exporter_factories(
    exporter_names: Collection[Tuple[str, str]],
) -> Collection[_SpanExporterFactory]:
    factories = []
    entry_points = {
        ep.name: ep for ep in iter_entry_points("opentelemetry_traces_exporter")
    }

    for name, internal_name in exporter_names:
        if internal_name not in entry_points:
            package = _KNOWN_EXPORTER_PACKAGES.get(internal_name)
            if package:
                help_msg = f"please make sure {package} is installed"
            else:
                help_msg = "please make sure the relevant exporter package is installed."
            raise ValueError(f'exporter "{name} ({internal_name})" not found. {help_msg}')

        exporter_class: _SpanExporterClass = entry_points[internal_name].load()
        if internal_name == _EXPORTER_OTLP_GRPC:
            factory = _otlp_factory
        else:
            factory = _generic_exporter
        factories.append(partial(factory, exporter_class))
    return factories


def _generic_exporter(
    exporter: _SpanExporterClass,
    options: _Options,  # pylint: disable=unused-argument
) -> SpanExporter:
    return exporter()


def _otlp_factory(exporter: _SpanExporterClass, options: "_Options") -> SpanExporter:
    return exporter(headers=(("x-sf-token", options.access_token),))
