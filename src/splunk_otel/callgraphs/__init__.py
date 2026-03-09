from opentelemetry import trace
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME

from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor
from splunk_otel.env import (
    Env,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
)

_DEFAULT_SNAPSHOT_SAMPLING_INTERVAL = 10


class CallgraphsState:
    """Runtime state of the Callgraph (aka snapshot) profiler, for OpAMP reporting."""

    def __init__(self, processor: "CallgraphsSpanProcessor | None", interval: int):
        self._processor = processor
        self._interval = interval

    def is_enabled(self) -> bool:
        return self._processor is not None

    def interval(self) -> int:
        if self._processor is not None:
            return self._processor.interval_millis()
        return self._interval


def _configure_callgraphs_if_enabled(env=None) -> CallgraphsState:
    env = env or Env()
    interval = env.getint(SPLUNK_SNAPSHOT_SAMPLING_INTERVAL, _DEFAULT_SNAPSHOT_SAMPLING_INTERVAL)
    if env.is_true(SPLUNK_SNAPSHOT_PROFILER_ENABLED):
        processor = CallgraphsSpanProcessor(env.getval(OTEL_SERVICE_NAME), interval)
        trace.get_tracer_provider().add_span_processor(processor)
        return CallgraphsState(processor, interval)
    return CallgraphsState(None, interval)
