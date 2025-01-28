import os
import time

from opentelemetry import trace
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME
from splunk_otel import init_splunk_otel
from splunk_otel.env import SPLUNK_ACCESS_TOKEN, SPLUNK_REALM

os.environ[OTEL_SERVICE_NAME] = "my-svc"
os.environ[SPLUNK_REALM] = "us1"
os.environ[SPLUNK_ACCESS_TOKEN] = "abc123"

# The `init_splunk_otel` function configures OTel metrics, traces, and logs.
init_splunk_otel()

tracer = trace.get_tracer("my-tracer")
for i in range(12):
    with tracer.start_as_current_span(f"my-span-{i}"):
        time.sleep(0.1)
