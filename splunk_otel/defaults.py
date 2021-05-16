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

_OTEL_SPAN_LINK_COUNT_LIMIT = "OTEL_SPAN_LINK_COUNT_LIMIT"
_OTEL_SPAN_LINK_COUNT_LIMIT_DEFAULT = "1000"

_OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT = "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT"
_OTEL_SPAN_EVENT_COUNT_LIMIT = "OTEL_SPAN_EVENT_COUNT_LIMIT"

_UNLIMITED = "999999"


def _set_otel_defaults() -> None:
    if _OTEL_SPAN_LINK_COUNT_LIMIT not in environ:
        environ[_OTEL_SPAN_LINK_COUNT_LIMIT] = _OTEL_SPAN_LINK_COUNT_LIMIT_DEFAULT

    if _OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT not in environ:
        environ[_OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT] = _UNLIMITED

    if _OTEL_SPAN_EVENT_COUNT_LIMIT not in environ:
        environ[_OTEL_SPAN_EVENT_COUNT_LIMIT] = _UNLIMITED
