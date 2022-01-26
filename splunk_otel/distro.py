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

from splunk_otel.options import _Options
from splunk_otel.tracing import _configure_tracing, _is_truthy

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


class _SplunkDistro(BaseDistro):
    def __init__(self):
        tracing_enabled = os.environ.get("OTEL_TRACE_ENABLED", True)
        self._tracing_enabled = _is_truthy(tracing_enabled)
        if not self._tracing_enabled:
            logger.info(
                "tracing has been disabled with OTEL_TRACE_ENABLED=%s", tracing_enabled
            )

    def _configure(self, **kwargs: Dict[str, Any]) -> None:
        if self._tracing_enabled:
            _configure_tracing(_Options())

    def load_instrumentor(self, entry_point: EntryPoint, **kwargs):
        if self._tracing_enabled:
            super().load_instrumentor(entry_point, **kwargs)
