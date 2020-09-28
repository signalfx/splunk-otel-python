import os
from typing import Sequence

from opentelemetry.exporter.zipkin import ZipkinSpanExporter as BaseZipkinSpanExporter
from opentelemetry.trace import Span


class ZipkinSpanExporter(BaseZipkinSpanExporter):
    def __init__(self, *args, **kwargs):
        self._max_attribute_length = int(os.environ.get("SPLK_MAX_ATTR_LENGTH", 0))
        super().__init__(*args, **kwargs)

    def _translate_to_zipkin(self, spans: Sequence[Span]):
        zipkin_spans = super()._translate_to_zipkin(spans)
        if not self._max_attribute_length:
            return zipkin_spans

        for span in zipkin_spans:
            tags = span.get("tags", {})
            for key, val in tags.items():
                if len(val) > self._max_attribute_length:
                    tags[key] = val[: self._max_attribute_length]
        return zipkin_spans
