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

import logging
from os import environ
from typing import Optional

from opentelemetry.sdk.resources import Resource

from splunk_otel.util import _is_truthy

logger = logging.getLogger(__name__)
_DEFAULT_CALL_STACK_INTERVAL_MILLIS = 1_000


def _sanitize_interval(interval):
    if isinstance(interval, int):
        if interval < 1:
            logger.warning(
                "call stack interval has to be positive, got %s, defaulting to %s",
                interval,
                _DEFAULT_CALL_STACK_INTERVAL_MILLIS,
            )
            return _DEFAULT_CALL_STACK_INTERVAL_MILLIS

        return interval

    logger.warning(
        "call stack interval not an integer, defaulting to %s",
        _DEFAULT_CALL_STACK_INTERVAL_MILLIS,
    )
    return _DEFAULT_CALL_STACK_INTERVAL_MILLIS


class _Options:
    resource: Resource
    endpoint: str
    call_stack_interval_millis: int

    def __init__(
        self,
        resource: Resource,
        endpoint: Optional[str] = None,
        call_stack_interval_millis: Optional[int] = None,
        include_internal_stacks: Optional[bool] = None,
    ):
        self.resource = resource
        self.endpoint = _Options._get_endpoint(endpoint)
        self.call_stack_interval_millis = _Options._get_call_stack_interval(
            call_stack_interval_millis
        )
        self.include_internal_stacks = _Options._include_internal_stacks(
            include_internal_stacks
        )

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
                return _sanitize_interval(int(interval))

            return _DEFAULT_CALL_STACK_INTERVAL_MILLIS

        return _sanitize_interval(interval)

    @staticmethod
    def _include_internal_stacks(include: Optional[bool]) -> bool:
        if include is None:
            return _is_truthy(environ.get("SPLUNK_PROFILER_INCLUDE_INTERNAL_STACKS"))

        return include
