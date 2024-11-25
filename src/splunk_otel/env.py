#  Copyright Splunk Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os

DEFAULTS = {
    "OTEL_PYTHON_LOG_CORRELATION": "true",  # FIXME: revisit
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",  # FIXME: revisit
    "OTEL_ATTRIBUTE_COUNT_LIMIT": "",
    "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "",
    "OTEL_SPAN_EVENT_COUNT_LIMIT": "",
    "OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT": "",
    "OTEL_LINK_ATTRIBUTE_COUNT_LIMIT": "",
    "OTEL_SPAN_LINK_COUNT_LIMIT": "1000",
    "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT": "12000",
    "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS": "host",
    "OTEL_TRACES_SAMPLER": "always_on",
}

OTEL_TRACE_ENABLED = "OTEL_TRACE_ENABLED"
OTEL_METRICS_ENABLED = "OTEL_METRICS_ENABLED"
OTEL_LOGS_ENABLED = "OTEL_LOGS_ENABLED"
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED = "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"

SPLUNK_OTEL_SYSTEM_METRICS_ENABLED = "SPLUNK_OTEL_SYSTEM_METRICS_ENABLED"
SPLUNK_ACCESS_TOKEN = "SPLUNK_ACCESS_TOKEN"  # noqa: S105
SPLUNK_TRACE_RESPONSE_HEADER_ENABLED = "SPLUNK_TRACE_RESPONSE_HEADER_ENABLED"
SPLUNK_PROFILER_ENABLED = "SPLUNK_PROFILER_ENABLED"

X_SF_TOKEN = "x-sf-token"  # noqa S105


class Env:
    """
    Wrapper around a system's environment variables with convenience methods.
    Defaults to using os.environ but you can pass in a dictionary for testing.
    """

    def __init__(self, store=None):
        self.store = os.environ if store is None else store

    def is_true(self, key, default=""):
        return is_true_str(self.getval(key, default))

    def list_append(self, key, value):
        curr = self.getval(key)
        if curr:
            curr += ","
        self.setval(key, curr + value)

    def getval(self, key, default=""):
        return self.store.get(key, default)

    def setval(self, key, value):
        self.store[key] = value

    def setdefault(self, key, value):
        self.store.setdefault(key, value)


def is_true_str(s: str) -> bool:
    return s.strip().lower() == "true"
