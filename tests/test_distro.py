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
from importlib.metadata import entry_points

from splunk_otel.distro import is_system_metrics_instrumentor, SplunkDistro
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


def test_is_system_metrics_instrumentor():
    eps = entry_points()

    ep = eps.get("opentelemetry_instrumentor")[0]
    assert is_system_metrics_instrumentor(ep)

    distro_ep = eps.get("opentelemetry_distro")[0]
    assert not is_system_metrics_instrumentor(distro_ep)
