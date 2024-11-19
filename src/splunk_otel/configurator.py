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

from opentelemetry.sdk._configuration import _OTelSDKConfigurator

from splunk_otel.env import SPLUNK_PROFILER_ENABLED, Env
from splunk_otel.profile import start_profiling


class SplunkConfigurator(_OTelSDKConfigurator):
    def _configure(self, **kwargs):
        super()._configure(**kwargs)
        if Env().is_true(SPLUNK_PROFILER_ENABLED):
            start_profiling()
