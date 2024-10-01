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

from opentelemetry.instrumentation.distro import BaseDistro

from splunk_otel.env import DEFAULTS, Env


class SplunkDistro(BaseDistro):
    """
    Loaded by the opentelemetry-instrumentation package via an entrypoint when running `opentelemetry-instrument`
    """

    def __init__(self):
        # can't accept an arg here because of the parent class
        self.env = Env()

    def _configure(self, **kwargs):
        self.set_env_defaults()

    def set_env_defaults(self):
        for key, value in DEFAULTS.items():
            self.env.setdefault(key, value)
