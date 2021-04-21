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

from typing import Any, Dict

from opentelemetry.instrumentation.distro import BaseDistro  # type: ignore

from splunk_otel.options import Options
from splunk_otel.tracing import _configure_tracing


class SplunkDistro(BaseDistro):
    def _configure(self, **kwargs: Dict[str, Any]) -> None:
        _configure_tracing(Options())
