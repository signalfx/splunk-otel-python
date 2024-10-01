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

from splunk_otel.distro import SplunkDistro
from splunk_otel.env import Env


def test_distro_env():
    env_store = {}
    # SplunkDistro's parent prevents passing in a constructor arg...
    sd = SplunkDistro()
    # ...so instead we overwrite the field right after construction
    sd.env = Env(env_store)
    sd.configure()
    # spot check default env vars
    assert env_store["OTEL_TRACES_EXPORTER"] == "otlp"
    assert len(env_store) == 11
