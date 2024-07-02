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
import os

from opentelemetry.instrumentation.propagators import get_global_response_propagator
from opentelemetry.sdk.trace import SpanLimits

from splunk_otel.distro import _SplunkDistro
from splunk_otel.propagators import _ServerTimingResponsePropagator


def test_distro_env(monkeypatch):
    monkeypatch.setenv("SPLUNK_ACCESS_TOKEN", "s4cr4t")
    sd = _SplunkDistro()
    sd.configure()
    assert os.getenv("OTEL_PYTHON_LOG_CORRELATION") == "true"
    assert os.getenv("OTEL_TRACES_EXPORTER") == "otlp"
    assert os.getenv("OTEL_METRICS_EXPORTER") == "otlp"
    assert os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") == "grpc"
    assert os.getenv("OTEL_EXPORTER_OTLP_HEADERS") == "x-sf-token=s4cr4t"
    assert os.getenv("OTEL_RESOURCE_ATTRIBUTES") == "splunk.distro.version=2.0"
    assert type(get_global_response_propagator()) is _ServerTimingResponsePropagator


def test_default_limits():
    _SplunkDistro().configure()
    limits = SpanLimits()
    assert limits.max_events is None
    assert limits.max_span_attributes is None
    assert limits.max_event_attributes is None
    assert limits.max_link_attributes is None

    assert limits.max_links == 1000
    assert limits.max_attribute_length == 12000
    assert limits.max_span_attribute_length == 12000
