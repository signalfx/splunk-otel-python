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
import logging
import os

from opentelemetry.environment_variables import OTEL_LOGS_EXPORTER, OTEL_METRICS_EXPORTER, OTEL_TRACES_EXPORTER
from opentelemetry.sdk.environment_variables import (
    OTEL_ATTRIBUTE_COUNT_LIMIT,
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
    OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
    OTEL_EXPERIMENTAL_RESOURCE_DETECTORS,
    OTEL_LINK_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
    OTEL_SPAN_EVENT_COUNT_LIMIT,
    OTEL_SPAN_LINK_COUNT_LIMIT,
    OTEL_TRACES_SAMPLER,
)

OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED = "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"

DEFAULTS = {
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED: "true",
    OTEL_TRACES_EXPORTER: "otlp",
    OTEL_METRICS_EXPORTER: "otlp",
    OTEL_LOGS_EXPORTER: "otlp",
    OTEL_ATTRIBUTE_COUNT_LIMIT: "",
    OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT: "",
    OTEL_SPAN_EVENT_COUNT_LIMIT: "",
    OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT: "",
    OTEL_LINK_ATTRIBUTE_COUNT_LIMIT: "",
    OTEL_SPAN_LINK_COUNT_LIMIT: "1000",
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: "12000",
    OTEL_EXPERIMENTAL_RESOURCE_DETECTORS: "host,process",
    OTEL_TRACES_SAMPLER: "always_on",
}

SPLUNK_OTEL_SYSTEM_METRICS_ENABLED = "SPLUNK_OTEL_SYSTEM_METRICS_ENABLED"
SPLUNK_ACCESS_TOKEN = "SPLUNK_ACCESS_TOKEN"  # noqa: S105
SPLUNK_TRACE_RESPONSE_HEADER_ENABLED = "SPLUNK_TRACE_RESPONSE_HEADER_ENABLED"
SPLUNK_PROFILER_ENABLED = "SPLUNK_PROFILER_ENABLED"
SPLUNK_PROFILER_CALL_STACK_INTERVAL = "SPLUNK_PROFILER_CALL_STACK_INTERVAL"
SPLUNK_PROFILER_LOGS_ENDPOINT = "SPLUNK_PROFILER_LOGS_ENDPOINT"
SPLUNK_REALM = "SPLUNK_REALM"

_pylogger = logging.getLogger(__name__)


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

    def getint(self, key, default=0):
        val = self.getval(key, str(default))
        try:
            return int(val)
        except ValueError:
            _pylogger.warning("Invalid integer value of '%s' for env var '%s'", val, key)
            return default

    def setval(self, key, value):
        self.store[key] = value

    def setdefault(self, key, value):
        self.store.setdefault(key, value)


def is_true_str(s: str) -> bool:
    return s.strip().lower() == "true"
