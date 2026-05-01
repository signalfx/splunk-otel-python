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
from splunk_otel.configurator import SplunkConfigurator
from splunk_otel.config_provider import get_config_provider
from splunk_otel.distro import SplunkDistro
from splunk_otel.env import Env


def init_splunk_otel():
    """
    Initializes OpenTelemetry Python components (exporters, tracer providers, meter providers, resources etc.).
    Like auto instrumentation (`opentelemetry-instrument`) but without loading instrumentors.
    """
    runtime_env = Env()
    provider = get_config_provider(runtime_env)
    sd = SplunkDistro(provider, runtime_env)
    sd.configure()
    sc = SplunkConfigurator(provider)
    sc.configure()
