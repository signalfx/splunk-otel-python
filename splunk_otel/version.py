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

import pkg_resources

pkg = pkg_resources.get_distribution("splunk-opentelemetry")

__version__ = pkg.version


def _format_version_info() -> str:
    lines = []
    lines.append(f"splunk-opentelemetry=={pkg.version}")
    lines.append("\n\nAlso uses the following OpenTelemetry libraries:\n")
    for dep in pkg.requires():
        if "opentelemetry" in getattr(dep, "name", ""):
            lines.append(f"\t{str(dep)}")

    return "\n".join(lines)
