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
from splunk_otel.profiling import _start_profiling
from splunk_otel.profiling.options import _Options as ProfilingOptions
from splunk_otel.util import _is_truthy
from opentelemetry.sdk._configuration import _OTelSDKConfigurator

logger = logging.getLogger(__name__)

class SplunkConfigurator(_OTelSDKConfigurator):
  pass


class _SplunkDistro(BaseDistro):
    def __init__(self):
        profiling_enabled = os.environ.get("SPLUNK_PROFILER_ENABLED", False)
        self._profiling_enabled = _is_truthy(profiling_enabled)

    def _configure(self, **kwargs: Dict[str, Any]) -> None:
        options = _Options()
        # FIXME _configure_Tracing and _metrics might have some unique stuff to copy thrugh to here

        if self._profiling_enabled:
            _start_profiling(ProfilingOptions(options.resource))
