# Copyright 2018, OpenCensus Authors
# Copyright The OpenTelemetry Authors
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

import base64
import logging
import socket

from thrift.protocol import TBinaryProtocol, TCompactProtocol
from thrift.transport import THttpClient, TTransport

from opentelemetry.configuration import Configuration
from opentelemetry.exporter.jaeger.gen.agent import Agent as agent
from opentelemetry.exporter.jaeger.gen.jaeger import Collector as jaeger
from opentelemetry.exporter.jaeger import (
    JaegerSpanExporter as BaseJaegerSpanExporter,
    _convert_int_to_i64,
    _extract_logs_from_span,
    _extract_refs_from_span,
    _extract_tags,
    _nsec_to_usec_round,
    _get_long_tag,
    _get_string_tag,
    _get_bool_tag,
    _get_trace_id_low,
    _get_trace_id_high,
)
from opentelemetry.sdk.trace.export import Span, SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

DEFAULT_AGENT_HOST_NAME = "localhost"
DEFAULT_AGENT_PORT = 6831

UDP_PACKET_MAX_LENGTH = 65000

OTLP_JAEGER_SPAN_KIND = {
    SpanKind.CLIENT: "client",
    SpanKind.SERVER: "server",
    SpanKind.CONSUMER: "consumer",
    SpanKind.PRODUCER: "producer",
}

logger = logging.getLogger(__name__)


class JaegerSpanExporter(BaseJaegerSpanExporter):

    def export(self, spans):
        jaeger_spans = _translate_to_jaeger(spans)

        batch = jaeger.Batch(
            spans=jaeger_spans,
            process=jaeger.Process(serviceName=self.service_name),
        )

        if self.collector is not None:
            self.collector.submit(batch)
        else:
            self.agent_client.emit(batch)

        return SpanExportResult.SUCCESS


def _translate_to_jaeger(spans: Span):
    """Translate the spans to Jaeger format.

    Args:
        spans: Tuple of spans to convert
    """

    jaeger_spans = []

    for span in spans:
        ctx = span.get_span_context()
        trace_id = ctx.trace_id
        span_id = ctx.span_id

        start_time_us = _nsec_to_usec_round(span.start_time)
        duration_us = _nsec_to_usec_round(span.end_time - span.start_time)

        status = span.status

        parent_id = span.parent.span_id if span.parent else 0

        tags = _extract_tags(span.attributes)
        tags.extend(_extract_tags(span.resource.attributes))

        tags.extend(
            [
                _get_long_tag("status.code", status.status_code.value),
                _get_string_tag("status.message", status.description),
                _get_string_tag(
                    "span.kind", _otlp_to_jaeger_span_kind(span.kind)
                ),
            ]
        )

        if span.instrumentation_info is not None:
            tags.extend(
                [
                    _get_string_tag(
                        "otel.instrumentation_library.name",
                        span.instrumentation_info.name,
                    ),
                    _get_string_tag(
                        "otel.instrumentation_library.version",
                        span.instrumentation_info.version,
                    ),
                ]
            )

        # Ensure that if Status.Code is not OK, that we set the "error" tag on the Jaeger span.
        if not status.is_ok:
            tags.append(_get_bool_tag("error", True))

        refs = _extract_refs_from_span(span)
        logs = _extract_logs_from_span(span)

        flags = int(ctx.trace_flags)

        jaeger_span = jaeger.Span(
            traceIdHigh=_get_trace_id_high(trace_id),
            traceIdLow=_get_trace_id_low(trace_id),
            # generated code expects i64
            spanId=_convert_int_to_i64(span_id),
            operationName=span.name,
            startTime=start_time_us,
            duration=duration_us,
            tags=tags,
            logs=logs,
            references=refs,
            flags=flags,
            parentSpanId=_convert_int_to_i64(parent_id),
        )

        jaeger_spans.append(jaeger_span)

    return jaeger_spans


def _otlp_to_jaeger_span_kind(kind: SpanKind) -> str:
    jaeger_kind = OTLP_JAEGER_SPAN_KIND.get(kind, "")
    if not jaeger_kind:
        jaeger_kind = kind.name.lower()
    return jaeger_kind
