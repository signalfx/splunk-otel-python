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
from opentelemetry.sdk.trace.export import SpanExporter

from splunk_otel.environment_variables import (
    _SPLUNK_ACCESS_TOKEN,
    _SPLUNK_TRACE_RESPONSE_HEADER_ENABLED,
)
from splunk_otel.propagators import _ServerTimingResponsePropagator
from splunk_otel.util import _is_truthy_str

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
