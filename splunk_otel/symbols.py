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

_DEFAULT_SERVICE_NAME = "unnamed-python-service"
_DEFAULT_EXPORTERS = "otlp"
_DEFAULT_JAEGER_ENDPOINT = "http://localhost:9080/v1/trace"
_DEFAULT_MAX_ATTR_LENGTH = 12000
_DEFAULT_SPAN_LINK_COUNT_LIMIT = 1000

_EXPORTER_OTLP = "otlp"
_EXPORTER_OTLP_GRPC = "otlp_proto_grpc"
_EXPORTER_JAEGER_THRIFT = "jaeger_thrift"
_EXPORTER_JAEGER_SPLUNK = "jaeger-thrift-splunk"
_DEFAULT_OTEL_SERVICE_NAME = "unknown_service"

_SPLUNK_DISTRO_VERSION_ATTR = "splunk.distro.version"
_SERVICE_NAME_ATTR = "service.name"
_TELEMETRY_VERSION_ATTR = "telemetry.auto.version"
_NO_SERVICE_NAME_WARNING = """service.name attribute is not set, your service is unnamed and will be difficult to identify.
set your service name using the OTEL_SERVICE_NAME environment variable.
E.g. `OTEL_SERVICE_NAME="<YOUR_SERVICE_NAME_HERE>"`"""

_KNOWN_EXPORTER_PACKAGES = {
    _EXPORTER_OTLP: "opentelemetry-exporter-otlp-proto-grpc",
    _EXPORTER_OTLP_GRPC: "opentelemetry-exporter-otlp-proto-grpc",
    _EXPORTER_JAEGER_THRIFT: "opentelemetry-exporter-jaeger-thrift",
    _EXPORTER_JAEGER_SPLUNK: "opentelemetry-exporter-jaeger-thrift",
}

_LIMIT_UNSET_VALUE = ""
