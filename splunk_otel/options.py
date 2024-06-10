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
from typing import Callable, Optional

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
from opentelemetry.sdk.trace.export import SpanExporter

from splunk_otel.environment_variables import (
    _SPLUNK_ACCESS_TOKEN,
    _SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
)
from splunk_otel.propagators import _ServerTimingResponsePropagator
from splunk_otel.symbols import (
    _DEFAULT_MAX_ATTR_LENGTH,
    _DEFAULT_SPAN_LINK_COUNT_LIMIT,
    _LIMIT_UNSET_VALUE,
    _SPLUNK_DISTRO_VERSION_ATTR,
)
from splunk_otel.util import _is_truthy_str
from splunk_otel.version import __version__

_SpanExporterFactory = Callable[["_Options"], SpanExporter]
_SpanExporterClass = Callable[..., SpanExporter]

logger = logging.getLogger("options")


# FIXME possibly deal with one-off customer issues with documenting how to customize
# span exporters with stock otel apis
class _Options:
    access_token: Optional[str]
    response_propagation: bool
    response_propagator: Optional[ResponsePropagator]

    def __init__(
        self,
        access_token: Optional[str] = None,
        trace_response_header_enabled: Optional[bool] = None,
    ):
        # todo: remove this side effect
        _set_default_env()

        self.access_token = _resolve_access_token(access_token)
        self.response_propagator = _get_response_propagator(trace_response_header_enabled)


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


# FIXME need our splunk.distro.version attribute added to the resource
#            _SPLUNK_DISTRO_VERSION_ATTR: __version__,


def _set_default_env() -> None:
    # FIXME audit this for same-as-upstream or unique-to-us
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
