---

<p align="center">
  <strong>
    <a href="https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.application">Get Started</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="CONTRIBUTING.md">Get Involved</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.otel.repo.migration">Migrating from SignalFx Python Tracing</a>
  </strong>
</p>

<p align="center">
  <span class="otel-version-badge"><a href="https://github.com/open-telemetry/opentelemetry-python/releases/tag/v1.27.0"><img alt="OpenTelemetry Python Version" src="https://img.shields.io/badge/otel-1.27.0-blueviolet?style=for-the-badge"/></a></span>
  <a href="https://github.com/signalfx/splunk-otel-python/releases">
    <img alt="GitHub release (latest SemVer)" src="https://img.shields.io/github/v/release/signalfx/splunk-otel-python?style=for-the-badge">
  </a>
  <a href="https://pypi.org/project/splunk-opentelemetry/">
    <img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/splunk-opentelemetry?style=for-the-badge">
  </a>
  <a href="https://github.com/signalfx/gdi-specification/releases/tag/v1.0.0">
    <img alt="Splunk GDI specification" src="https://img.shields.io/badge/GDI-1.0.0-blueviolet?style=for-the-badge">
  </a>
  <a href="https://codecov.io/gh/signalfx/splunk-otel-python">
    <img alt="Codecov" src="https://img.shields.io/codecov/c/github/signalfx/splunk-otel-python?style=for-the-badge&token=XKXjEQKGaK">
  </a>
  <a href="https://github.com/signalfx/splunk-otel-python/actions?query=workflow%3ATests">
    <img alt="Build Status" src="https://img.shields.io/github/workflow/status/signalfx/splunk-otel-python/Tests?style=for-the-badge">
  </a>
</p>

<p align="center">
  <strong>
    <a href="https://github.com/signalfx/tracing-examples/tree/main/opentelemetry-tracing/opentelemetry-python-tracing">Examples</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="SECURITY.md">Security</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation/README.md">Supported Libraries</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.troubleshooting">Troubleshooting</a>
  </strong>
</p>

# Splunk Distribution of OpenTelemetry Python

The Splunk distribution of [OpenTelemetry
Python](https://github.com/open-telemetry/opentelemetry-python) provides
multiple installable packages that automatically instrument your Python
application to capture and report distributed traces to Splunk APM.
Instrumentation works by patching supported libraries at runtime with an
OpenTelemetry-compatible tracer to capture and export trace spans.

This distribution comes with the following defaults:

- [W3C tracecontext](https://www.w3.org/TR/trace-context/) and [W3C
  baggage](https://www.w3.org/TR/baggage/) context propagation;
  [B3](https://github.com/openzipkin/b3-propagation) can also be
  [configured](https://docs.splunk.com/Observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html).
- [OTLP gRPC
  exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
  configured to send spans to a locally running [Splunk OpenTelemetry
  Connector](https://github.com/signalfx/splunk-otel-collector)
  (`http://localhost:4317`).
- Unlimited default limits for [configuration options](https://docs.splunk.com/Observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html) to
  support full-fidelity traces.

If you're currently using the SignalFx Tracing Library for Python and want to
migrate to the Splunk Distribution of OpenTelemetry Python, see [Migrate from
the SignalFx Tracing Library for Python](https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.otel.repo.migration).

---

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
See [the license file](./LICENSE) for more details.
