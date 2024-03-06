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
from opentelemetry.sdk.environment_variables import OTEL_SERVICE_NAME

from oteltest.common import OtelTest, Telemetry, trace_attribute_as_str_array

SERVICE_NAME = "sop-integration-test"

num_adds = 12


class SplunkSimpleTest(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {OTEL_SERVICE_NAME: SERVICE_NAME}

    def wrapper_script(self):
        return "splunk-py-trace"

    def is_enabled(self) -> bool:
        return True

    def requirements(self) -> Sequence[str]:
        return ("splunk-opentelemetry[all]",)

    def validate(self, t: Telemetry) -> None:
        for tr in t.get_traces():
            found_svc_names = trace_attribute_as_str_array(tr, "service.name")
            assert SERVICE_NAME == found_svc_names[0]  # noqa: S101
        assert num_adds == t.num_traces()  # noqa: S101

    def should_teardown(self) -> bool:
        return True


if __name__ == "__main__":
    counter = metrics.get_meter("my-meter").create_counter("my-counter")
    tracer = trace.get_tracer("my-tracer")
    for _ in range(num_adds):
        with tracer.start_as_current_span("my-span"):
            time.sleep(0.5)
            counter.add(1)
