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

- [W3C tracecontext](https://www.w3.org/TR/trace-context/) and [W3C baggage](https://www.w3.org/TR/baggage/)
  context propagation;
  [B3](https://github.com/openzipkin/b3-propagation) can also be
  [configured](https://docs.splunk.com/Observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html).
- [OTLP gRPC exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
  configured to send spans to a locally running
  [Splunk OpenTelemetry Connector](https://github.com/signalfx/splunk-otel-collector)
  (`http://localhost:4317`).
- Unlimited default limits for 
  [configuration options](https://docs.splunk.com/Observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html)
  to support full-fidelity traces.

## Requirements

This Splunk Distribution of OpenTelemetry requires Python 3.7 or later. Supported
libraries are listed
[here](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation).

## Get started

For complete instructions on how to get started with the Splunk Distribution of OpenTelemetry Python, see [Instrument a Python application for Splunk Observability Cloud](https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.application) in the official documentation.


# License

The Splunk distribution of OpenTelemetry Python Instrumentation is a
distribution of [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python).
It is licensed under the terms of the Apache Software License version 2.0.
See [the license file](./LICENSE.txt) for more details.
