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
import os
from typing import Collection, Dict, Optional, Union

from opentelemetry import trace
from opentelemetry.instrumentation.environment_variables import (
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS,
)
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pkg_resources import iter_entry_points

from splunk_otel.options import _Options, _SpanExporterFactory
from splunk_otel.util import _is_truthy

logger = logging.getLogger(__name__)

def start_tracing(
    service_name: Optional[str] = None,
    span_exporter_factories: Optional[Collection[_SpanExporterFactory]] = None,
    access_token: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Union[str, bool, int, float]]] = None,
    trace_response_header_enabled: Optional[bool] = None,
) -> trace.TracerProvider:
    # FIXME mark as deprecated or document the change or something
    # FIXME document new ways to either use otel apis or ours to do same config work
    # (x 5 fields)
    # FIXME posibly log
    return trace.get_tracer_provider()


