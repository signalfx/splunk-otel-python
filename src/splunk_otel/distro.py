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

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.propagators import set_global_response_propagator
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator

from splunk_otel.config_provider import ConfigProvider, get_config_provider
from splunk_otel.env import Env
from splunk_otel.propagator import CallgraphsPropagator, ServerTimingResponsePropagator

if TYPE_CHECKING:
    from typing_extensions import Self

_NO_SERVICE_NAME_WARNING = """The service.name attribute is not set, which may make your service difficult to identify.
Set your service name using the OTEL_SERVICE_NAME environment variable.
e.g. `OTEL_SERVICE_NAME="<YOUR_SERVICE_NAME_HERE>"`"""

_pylogger = logging.getLogger(__name__)


class SplunkDistro(BaseDistro):
    """
    Loaded by the opentelemetry-instrumentation package via an entrypoint when running `opentelemetry-instrument`
    """

    _splunk_instance: ClassVar[SplunkDistro | None] = None

    # The upstream singleton __new__ forwards constructor args to object.__new__,
    # so keep a local version that supports our optional args.
    def __new__(
        cls,
        *_args,
        **_kwargs,
    ) -> Self:
        instance = cls._splunk_instance
        if instance is None:
            instance = object.__new__(cls)
            cls._splunk_instance = instance
        return instance

    def __init__(
        self,
        config_provider: ConfigProvider | None = None,
        env: Env | None = None,
    ):
        self.env = env or Env()
        self.config_provider = config_provider or get_config_provider(self.env)

    def _configure(self, **kwargs):
        if self.config_provider.defaulted_service_name():
            _pylogger.warning(_NO_SERVICE_NAME_WARNING)
        self.config_provider.apply_upstream_to_env(self.env)

        self.set_server_timing_propagator()
        self.set_callgraphs_propagator()
        # Previously, the SDK's LoggingHandler was enabled by setting
        # OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true (our default). That handler
        # has been deprecated in the SDK and moved to opentelemetry-instrumentation-logging.
        # We call instrument() explicitly here to ensure the handler is installed for users
        # who don't run under `opentelemetry-instrument` (which would auto-discover it via
        # entry points). This is safe when running under `opentelemetry-instrument` because
        # LoggingInstrumentor is a singleton and its instrument() call is idempotent.
        LoggingInstrumentor().instrument()

    def set_server_timing_propagator(self):
        if self.config_provider.trace_response_header_enabled():
            set_global_response_propagator(ServerTimingResponsePropagator())

    def set_callgraphs_propagator(self):
        # Strip any existing CallgraphsPropagator before conditionally adding a fresh one,
        # so this method is idempotent and the result depends only on the current config.
        current = get_global_textmap()
        if isinstance(current, CompositePropagator):
            current_propagators = current._propagators  # noqa: SLF001
            propagators = [p for p in current_propagators if not isinstance(p, CallgraphsPropagator)]
        else:
            propagators = [current]

        if self.config_provider.snapshot_profiler_enabled():
            propagators.append(CallgraphsPropagator(self.config_provider.snapshot_selection_probability()))

        set_global_textmap(CompositePropagator(propagators))
