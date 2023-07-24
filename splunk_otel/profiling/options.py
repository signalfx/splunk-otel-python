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

from os import environ
from typing import Optional

from opentelemetry.sdk.resources import Resource


class _Options:
    resource: Resource
    endpoint: str
    call_stack_interval: int

    def __init__(
        self,
        resource: Resource,
        endpoint: Optional[str] = None,
        call_stack_interval: Optional[int] = None,
    ):
        self.resource = resource
        self.endpoint = _Options._get_endpoint(endpoint)
        self.call_stack_interval = _Options._get_call_stack_interval(call_stack_interval)

    @staticmethod
    def _get_endpoint(endpoint: Optional[str]) -> str:
        if not endpoint:
            endpoint = environ.get("SPLUNK_PROFILER_LOGS_ENDPOINT")

        if not endpoint:
            endpoint = environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

        return endpoint or "http://localhost:4317"

    @staticmethod
    def _get_call_stack_interval(interval: Optional[int]) -> int:
        if not interval:
            interval = environ.get("SPLUNK_PROFILER_CALL_STACK_INTERVAL")

            if interval:
                return int(interval)

        return 1_000
