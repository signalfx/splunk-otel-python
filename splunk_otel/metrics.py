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

import logging
import os

from opentelemetry.sdk.metrics import MeterProvider

from splunk_otel.util import _is_truthy

logger = logging.getLogger(__name__)


def start_metrics() -> MeterProvider:
    # pylint: disable=import-outside-toplevel
    from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

    enabled = os.environ.get("OTEL_METRICS_ENABLED", True)
    if not _is_truthy(enabled):
        logger.info("metering has been disabled with OTEL_METRICS_ENABLED=%s", enabled)
        return None

    try:
        meter_provider = _configure_metrics()
        system_metrics = SystemMetricsInstrumentor()
        system_metrics.instrument(meter_provider=meter_provider)
        logger.debug("Instrumented runtime metrics")
        return meter_provider
    except Exception as exc:  # pylint:disable=broad-except
        logger.exception("Instrumenting of runtime metrics failed")
        raise exc


def _configure_metrics() -> MeterProvider:
    # pylint: disable=import-outside-toplevel
    # FIXME yes, this doesn't match up to the spec in terms of looking for
    # relevant environment variables, etc., but this is a stopgap because a lot
    # of this initialization sequence needs to be burned down and replaced with the
    # upstream SDK's Configurator.
    metrics_exporter = None
    try:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )

        metrics_exporter = OTLPMetricExporter()
    except Exception:  # pylint:disable=broad-except
        logger.info("Cannot load grpc metrics exporter, trying http/protobuf")
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )

        metrics_exporter = OTLPMetricExporter()

    from opentelemetry.metrics import set_meter_provider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    meter_provider = MeterProvider([PeriodicExportingMetricReader(metrics_exporter)])
    set_meter_provider(meter_provider)
    return meter_provider
