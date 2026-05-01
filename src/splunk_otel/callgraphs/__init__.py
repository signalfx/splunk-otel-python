from opentelemetry import trace

from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor


def configure_callgraphs(service_name: str, sampling_interval: int):
    trace.get_tracer_provider().add_span_processor(
        CallgraphsSpanProcessor(
            service_name,
            sampling_interval,
        )
    )
