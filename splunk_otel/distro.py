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
import os
from typing import Any, Dict

from opentelemetry.instrumentation.distro import BaseDistro  # type: ignore
from pkg_resources import EntryPoint

from splunk_otel.metrics import _configure_metrics
from splunk_otel.options import _Options
from splunk_otel.profiling import _start_profiling
from splunk_otel.profiling.options import _Options as ProfilingOptions
from splunk_otel.tracing import _configure_tracing
from splunk_otel.util import _is_truthy

logger = logging.getLogger(__name__)


class _SplunkDistro(BaseDistro):
    def __init__(self):
        tracing_enabled = os.environ.get("OTEL_TRACE_ENABLED", True)
        profiling_enabled = os.environ.get("SPLUNK_PROFILER_ENABLED", False)
        self._tracing_enabled = _is_truthy(tracing_enabled)
        self._profiling_enabled = _is_truthy(profiling_enabled)
        if not self._tracing_enabled:
            logger.info(
                "tracing has been disabled with OTEL_TRACE_ENABLED=%s", tracing_enabled
            )

        metrics_enabled = os.environ.get("OTEL_METRICS_ENABLED", True)
        self._metrics_enabled = _is_truthy(metrics_enabled)
        if not self._metrics_enabled:
            logger.info(
                "metering has been disabled with OTEL_METRICS_ENABLED=%s", metrics_enabled
            )

    def _configure(self, **kwargs: Dict[str, Any]) -> None:
        options = _Options()

        if self._tracing_enabled:
            _configure_tracing(options)

        if self._profiling_enabled:
            _start_profiling(ProfilingOptions(options.resource))

        if self._metrics_enabled:
            _configure_metrics()

    def load_instrumentor(self, entry_point: EntryPoint, **kwargs):
        if self._tracing_enabled:
            super().load_instrumentor(entry_point, **kwargs)
