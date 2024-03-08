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

import time
from typing import Mapping, Sequence

from opentelemetry import metrics, trace

from oteltest.common import OtelTest, Telemetry, trace_attribute_as_str_array

ACCESS_TOKEN = "abc123"
SERVICE_NAME = "sop-integration-test"
NUM_ADDS = 12

if __name__ == "__main__":
    counter = metrics.get_meter("my-meter").create_counter("my-counter")
    tracer = trace.get_tracer("my-tracer")
    for _ in range(NUM_ADDS):
        with tracer.start_as_current_span("my-span"):
            time.sleep(0.5)
            counter.add(1)


class SplunkOtelPythonTest(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {
            "OTEL_SERVICE_NAME": SERVICE_NAME,
            "SPLUNK_ACCESS_TOKEN": ACCESS_TOKEN,
        }

    def wrapper_script(self):
        return "splunk-py-trace"

    def requirements(self) -> Sequence[str]:
        return ("splunk-opentelemetry[all]",)

    def validate(self, telem: Telemetry) -> None:
        self.validate_traces(telem)
        self.validate_metrics(telem)
        assert telem.has_header("x-sf-token", "abc123")
        # todo test _ServerTimingResponsePropagator

    def validate_traces(self, t):
        for req in t.get_trace_requests():
            found_svc_names = trace_attribute_as_str_array(req.request, "service.name")
            for svc_name in found_svc_names:
                assert SERVICE_NAME == svc_name  # noqa: S101
        assert NUM_ADDS == t.num_spans()  # noqa: S101

    def validate_metrics(self, t):
        expected = {
            'my-counter',
            'system.cpu.time',
            'system.cpu.utilization',
            'system.memory.usage',
            'system.memory.utilization',
            'system.swap.usage',
            'system.swap.utilization',
            'system.disk.io',
            'system.disk.operations',
            'system.disk.time',
            'system.network.dropped_packets',
            'system.network.packets',
            'system.network.errors',
            'system.network.io',
            'system.thread_count',
            'process.runtime.cpython.memory',
            'process.runtime.cpython.cpu_time',
            'process.runtime.cpython.gc_count',
            'process.runtime.cpython.thread_count',
            'process.runtime.cpython.cpu.utilization',
            'process.runtime.cpython.context_switches',
        }
        assert expected == t.metric_names()
