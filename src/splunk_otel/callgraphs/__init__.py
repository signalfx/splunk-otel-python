from opentelemetry import trace
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME

from splunk_otel.callgraphs.span_processor import CallgraphsSpanProcessor
from splunk_otel.env import (
    Env,
    SPLUNK_SNAPSHOT_PROFILER_ENABLED,
    SPLUNK_SNAPSHOT_SAMPLING_INTERVAL,
)


def start_callgraphs_if_enabled(env=None):
    env = env or Env()
    if env.is_true(SPLUNK_SNAPSHOT_PROFILER_ENABLED):
        trace.get_tracer_provider().add_span_processor(
            CallgraphsSpanProcessor(env.getval(OTEL_SERVICE_NAME), env.getint(SPLUNK_SNAPSHOT_SAMPLING_INTERVAL, 10))
        )
