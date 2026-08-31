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

from typing import Protocol

from opentelemetry.instrumentation.environment_variables import OTEL_PYTHON_DISABLED_INSTRUMENTATIONS
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from splunk_otel.env import Env

_DISABLED_INSTRUMENTATIONS_WILDCARD = "*"
_LOGGING_INSTRUMENTATION_NAME = "logging"
_SERVER_TIMING_DEFAULT_ENABLED = True


class _LoggingInstrumentor(Protocol):
    def instrument(self) -> None: ...


def configure_logging_instrumentation(
    env: Env,
    logging_instrumentor: _LoggingInstrumentor | None = None,
) -> None:
    # The SDK LoggingHandler is deprecated. Install its replacement explicitly
    # for callers that do not use opentelemetry-instrument auto-discovery. This
    # is safe with auto-discovery because LoggingInstrumentor is a singleton and
    # instrument() is idempotent.
    if _is_instrumentation_disabled(env, _LOGGING_INSTRUMENTATION_NAME):
        return
    instrumentor = logging_instrumentor if logging_instrumentor is not None else LoggingInstrumentor()
    instrumentor.instrument()


def _is_instrumentation_disabled(env: Env, instrumentation_name: str) -> bool:
    disabled = env.getval(OTEL_PYTHON_DISABLED_INSTRUMENTATIONS)
    disabled_instrumentations = [name.strip() for name in disabled.split(",")]
    return (
        _DISABLED_INSTRUMENTATIONS_WILDCARD in disabled_instrumentations
        or instrumentation_name in disabled_instrumentations
    )
