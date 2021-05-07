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
from typing import Any, Collection, Dict, Mapping, Optional, Set, Tuple, Union

from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.instrumentation.propagators import ResponsePropagator
from opentelemetry.sdk.environment_variables import OTEL_RESOURCE_ATTRIBUTES
from pkg_resources import iter_entry_points

from splunk_otel.propagators import ServerTimingResponsePropagator
from splunk_otel.symbols import (
    _EXPORTER_JAEGER_SPLUNK,
    _EXPORTER_JAEGER_THRIFT,
    _EXPORTER_OTLP,
    _EXPORTER_OTLP_GRPC,
    _KNOWN_EXPORTER_PACKAGES,
    _NO_SERVICE_NAME_WARNING,
    _OTEL_EXPORTER_JAEGER_ENDPOINT,
    _SERVICE_NAME_ATTR,
    _TELEMETRY_VERSION_ATTR,
    DEFAULT_EXPORTERS,
    DEFAULT_JAEGER_ENDPOINT,
    DEFAULT_MAX_ATTR_LENGTH,
    DEFAULT_SERVICE_NAME,
)
from splunk_otel.types import ExporterFactory
from splunk_otel.version import __version__

logger = logging.getLogger("options")


class Options:
    exporter_factories: Collection[ExporterFactory]
    access_token: Optional[str]
    max_attr_length: int
    resource_attributes: Dict[str, Union[str, bool, int, float]]
    response_propagator: Optional[ResponsePropagator]

    def __init__(
        self,
        exporter_factories: Optional[Collection[ExporterFactory]] = None,
        access_token: Optional[str] = None,
        max_attr_length: Optional[int] = None,
        resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
        trace_response_header_enabled: Optional[bool] = None,
    ):

        if not access_token:
            access_token = _splunk_env_var("ACCESS_TOKEN")
        self.access_token = access_token or None

        if not max_attr_length:
            value = _splunk_env_var("MAX_ATTR_LENGTH")
            if value:
                try:
                    max_attr_length = int(value)
                except (TypeError, ValueError):
                    logger.error("SPLUNK_MAX_ATTR_LENGTH must be a number.")
        self.max_attr_length = max_attr_length or DEFAULT_MAX_ATTR_LENGTH

        if not resource_attributes:
            resource_attributes = {}
            env_value = environ.get(OTEL_RESOURCE_ATTRIBUTES, "").strip()
            if env_value:
                resource_attributes = {
                    key.strip(): value.strip()
                    for key, value in (pair.split("=") for pair in env_value.split(","))
                }
        self.resource_attributes = resource_attributes or {}

        self.resource_attributes.update({_TELEMETRY_VERSION_ATTR: __version__})
        if _SERVICE_NAME_ATTR not in self.resource_attributes:
            logger.warning(_NO_SERVICE_NAME_WARNING)
            self.resource_attributes[_SERVICE_NAME_ATTR] = DEFAULT_SERVICE_NAME

        if trace_response_header_enabled is None:
            trace_response_header_enabled = self._is_truthy(
                _splunk_env_var("TRACE_RESPONSE_HEADER_ENABLED", "true")
            )
        self.response_propagator = (
            ServerTimingResponsePropagator() if trace_response_header_enabled else None
        )

        if not exporter_factories:
            exporter_names = self._get_exporter_names_from_env()
            exporter_factories = self._import_exporter_factories(exporter_names)
        self.exporter_factories = exporter_factories

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

    @classmethod
    def _get_exporter_names_from_env(cls) -> Collection[Tuple[str, str]]:
        exporters_env = environ.get(OTEL_TRACES_EXPORTER, "").strip() or DEFAULT_EXPORTERS

        exporters: Set[Tuple[str, str]] = set()
        if not cls._is_truthy(exporters_env):
            return exporters

        # exporters are known by different names internally by Python Otel SDK.
        # Here we create a mapping of user provided names to internal names so
        # that we can provide helpful error messages later.
        for name in exporters_env.split(","):
            if name == _EXPORTER_OTLP:
                exporters.add((_EXPORTER_OTLP, _EXPORTER_OTLP_GRPC))
            elif name == _EXPORTER_JAEGER_SPLUNK:
                exporters.add((_EXPORTER_JAEGER_SPLUNK, _EXPORTER_JAEGER_THRIFT))
            else:
                exporters.add(
                    (
                        name,
                        name,
                    )
                )
        return exporters

    def _import_exporter_factories(
        self, exporter_names: Collection[Tuple[str, str]]
    ) -> Collection[ExporterFactory]:
        exporters = []
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

            exporter = entry_points[internal_name].load()
            exporter_kwargs = self.get_exporter_kwargs(name, internal_name)
            if exporter_kwargs:
                exporter = partial(exporter, **exporter_kwargs)
            exporters.append(exporter)
        return exporters

    def get_exporter_kwargs(self, name: str, internal_name: str) -> Mapping[Any, Any]:
        if internal_name == _EXPORTER_JAEGER_THRIFT:
            kwargs: Dict[Any, Any] = {
                "max_tag_value_length": self.max_attr_length,
            }

            if name == _EXPORTER_JAEGER_SPLUNK:
                kwargs["collector_endpoint"] = environ.get(
                    _OTEL_EXPORTER_JAEGER_ENDPOINT, DEFAULT_JAEGER_ENDPOINT
                )

            if self.access_token:
                kwargs.update(
                    {
                        "username": "auth",
                        "password": self.access_token,
                    }
                )
            return kwargs

        if internal_name == _EXPORTER_OTLP_GRPC:
            # TODO: enable after PR is merged and released:
            # https://github.com/open-telemetry/opentelemetry-python/pull/1824
            # kwargs = {"max_attr_value_length": self.max_attr_length}
            kwargs = {}
            if self.access_token:
                kwargs["headers"] = (("x-sf-token", self.access_token),)
            return kwargs
        return {}


def _splunk_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    old_key = "SPLK_{0}".format(name)
    new_key = "SPLUNK_{0}".format(name)
    if old_key in environ:
        logger.warning(
            "%s is deprecated and will be removed soon. Please use %s instead",
            old_key,
            new_key,
        )
        return environ[old_key]
    return environ.get(new_key, default)
