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

"""The Splunk distribution of OpenTelemetry Python provides multiple
installable packages that automatically instruments your Python
application to capture and report distributed traces to Splunk APM.

https://github.com/signalfx/splunk-otel-python
"""

from .defaults import _set_otel_defaults

_set_otel_defaults()

# pylint: disable=wrong-import-position
from .tracing import start_tracing  # noqa: E402
from .version import __version__  # noqa: E402
