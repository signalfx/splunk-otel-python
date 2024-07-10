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

import pytest
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.propagators import get_global_response_propagator
from opentelemetry.sdk.trace import SpanLimits

from splunk_otel.distro import SplunkConfigurator, SplunkDistro
from splunk_otel.propagators import _ServerTimingResponsePropagator


@pytest.fixture
def restore_env():
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


def test_distro_env(restore_env):
    os.environ["SPLUNK_ACCESS_TOKEN"] = "s4cr4t"

    sd = SplunkDistro()
    sd.configure()
    assert os.getenv("OTEL_PYTHON_LOG_CORRELATION") == "true"
    assert os.getenv("OTEL_TRACES_EXPORTER") == "otlp"
    assert os.getenv("OTEL_METRICS_EXPORTER") == "otlp"
    assert os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") == "grpc"
    assert os.getenv("OTEL_EXPORTER_OTLP_HEADERS") == "x-sf-token=s4cr4t"
    assert os.getenv("OTEL_RESOURCE_ATTRIBUTES") == "splunk.distro.version=2.0"
    assert isinstance(get_global_response_propagator(), _ServerTimingResponsePropagator)


def test_default_limits(restore_env):
    # we're not testing SplunkDistro here but configure() sets environment variables read by SpanLimits
    distro = SplunkDistro()
    distro.configure()

    # SpanLimits() is instantiated by the TracerProvider constructor
    # for testing, we instantiate it directly
    limits = SpanLimits()
    assert limits.max_events is None
    assert limits.max_span_attributes is None
    assert limits.max_event_attributes is None
    assert limits.max_link_attributes is None

    assert limits.max_links == 1000
    assert limits.max_attribute_length == 12000
    assert limits.max_span_attribute_length == 12000


def test_configurator():
    # we're not testing SplunkDistro here but configure() sets environment variables read by SplunkConfigurator
    distro = SplunkDistro()
    distro.configure()

    sp = SplunkConfigurator()
    sp.configure()
    tp = trace.get_tracer_provider()
    sync_multi_span_proc = getattr(tp, "_active_span_processor")
    assert len(sync_multi_span_proc._span_processors) == 1
    batch_span_processor = sync_multi_span_proc._span_processors[0]
    otlp_span_exporter = batch_span_processor.span_exporter
    assert isinstance(otlp_span_exporter, OTLPSpanExporter)
