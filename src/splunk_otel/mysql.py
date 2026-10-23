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

from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.trace import NonRecordingSpan, SpanContext, set_span_in_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_logger = logging.getLogger(__name__)


def execute_with_trace_context(connection, query_method, span_context: SpanContext, *args, **kwargs):
    """Experimental helper for one buffered, single-result MySQL execution.

    The caller supplies the unwrapped connection and the database CLIENT span's
    context. All earlier results must be consumed. Driver hooks must enforce
    these constraints before using this helper with customer queries.
    """
    carrier = {}
    # An explicit context prevents an invalid database span from injecting a parent.
    context = set_span_in_context(NonRecordingSpan(span_context))
    TraceContextTextMapPropagator().inject(carrier, context=context)
    try:
        _set_traceparent(connection, carrier.get("traceparent"), phase="setup")
        return query_method(*args, **kwargs)
    finally:
        # Attempt cleanup even if setup failed after the server accepted its SET.
        _set_traceparent(connection, None, phase="cleanup")


def _set_traceparent(connection, value, *, phase):
    try:
        with suppress_instrumentation():
            cursor = connection.cursor()
            try:
                cursor.execute("SET @traceparent = %s", (value,))
            finally:
                cursor.close()
    except Exception as error:  # noqa: BLE001 - Internal commands must not replace the query result or error.
        _logger.warning("MySQL trace context %s failed (%s)", phase, type(error).__name__)
