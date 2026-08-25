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

import pytest

from splunk_otel.env import Env
from splunk_otel.runtime import configure_logging_instrumentation


class _FakeLoggingInstrumentor:
    def __init__(self):
        self.instrument_calls = 0

    def instrument(self) -> None:
        self.instrument_calls += 1


@pytest.mark.parametrize(
    "disabled_instrumentations",
    [
        "logging",
        "requests,logging,flask",
        "requests, logging , flask",
        "*",
    ],
)
def test_logging_instrumentation_respects_disabled_instrumentations(disabled_instrumentations):
    logging_instrumentor = _configure_logging({"OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": disabled_instrumentations})
    assert logging_instrumentor.instrument_calls == 0


def test_logging_instrumentation_is_enabled_when_not_disabled():
    logging_instrumentor = _configure_logging({"OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "requests,flask"})
    assert logging_instrumentor.instrument_calls == 1


def _configure_logging(env_store):
    logging_instrumentor = _FakeLoggingInstrumentor()
    configure_logging_instrumentation(Env(env_store), logging_instrumentor)
    return logging_instrumentor
