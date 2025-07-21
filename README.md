# splunk-opentelemetry

[![PyPI - Version](https://img.shields.io/pypi/v/splunk-opentelemetry.svg)](https://pypi.org/project/splunk-opentelemetry)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/splunk-opentelemetry.svg)](https://pypi.org/project/splunk-opentelemetry)

-----

# Splunk Distribution of OpenTelemetry Python

The Splunk distribution of [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python) provides
multiple installable packages that automatically instrument your Python application to capture and report distributed
traces to Splunk APM. Instrumentation works by patching supported libraries at runtime with an OpenTelemetry-compatible
tracer to capture and export trace spans.

This distribution comes with the following defaults:

- [OTLP gRPC exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
  configured to send spans to a locally running
  [Splunk OpenTelemetry Collector](https://github.com/signalfx/splunk-otel-collector)
  (`http://localhost:4317`).
- Unlimited default limits for 
  [configuration options](https://docs.splunk.com/Observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html)
  to support full-fidelity traces.
- Inclusion of [system metrics](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation/opentelemetry-instrumentation-system-metrics)

## Requirements

This Splunk Distribution of OpenTelemetry requires Python 3.9 or later. Supported
libraries are listed
[here](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation).

## Get started

For complete instructions on how to get started with the Splunk Distribution of OpenTelemetry Python, see
[Instrument a Python application for Splunk Observability Cloud](https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.application) in the official documentation.


# License

The Splunk distribution of OpenTelemetry Python Instrumentation is a
distribution of [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python).
It is licensed under the terms of the Apache Software License version 2.0.
See [the license file](./LICENSE.txt) for more details.

# Deprecation
ℹ️ The Splunk Distribution of OpenTelemetry Python version 1.X is deprecated as of February 28, 2025 and will reach end of
support on February 28, 2026. Existing customers should consider migrating to Splunk OpenTelemetry Python 2.0 or higher.
See [Migrate to the Splunk Python 2.0 instrumentation](https://docs.splunk.com/observability/en/gdi/get-data-in/application/python/migration-guide.html#python-migration-guide).

