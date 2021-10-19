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

from opentelemetry import trace

from splunk_otel import start_tracing

provider = start_tracing()

tracer = trace.get_tracer("simple", "0.1")


def main():
    with tracer.start_as_current_span(
        "custom span", kind=trace.SpanKind.INTERNAL
    ) as span:
        span.add_event("event1", {"k1": "v1"})


if __name__ == "__main__":
    main()
    provider.force_flush()
    provider.shutdown()
