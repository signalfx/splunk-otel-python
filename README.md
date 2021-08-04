---

<p align="center">
  <strong>
    <a href="#getting-started">Getting Started</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="CONTRIBUTING.md">Getting Involved</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="MIGRATING.md">Migrating from SignalFx Python Tracing</a>
  </strong>
</p>

<p align="center">
  <span class="otel-version-badge"><a href="https://github.com/open-telemetry/opentelemetry-python/releases/tag/v1.4.1"><img alt="OpenTelemetry Python Version" src="https://img.shields.io/badge/otel-1.4.1-blueviolet?style=for-the-badge"/></a></span>
  <a href="https://github.com/signalfx/splunk-otel-python/releases">
    <img alt="GitHub release (latest SemVer)" src="https://img.shields.io/github/v/release/signalfx/splunk-otel-python?style=for-the-badge">
  </a>
  <a href="https://pypi.org/project/splunk-opentelemetry/">
    <img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/splunk-opentelemetry?style=for-the-badge">
  </a>
  <a href="https://circleci.com/gh/signalfx/splunk-otel-python">
    <img alt="CircleCI" src="https://img.shields.io/circleci/build/github/signalfx/splunk-otel-python/main?style=for-the-badge">
  </a>
  <a href="https://codecov.io/gh/signalfx/splunk-otel-python">
    <img alt="Codecov" src="https://img.shields.io/codecov/c/github/signalfx/splunk-otel-python?style=for-the-badge&token=XKXjEQKGaK">
  </a>
</p>

<p align="center">
  <strong>
    <a href="https://github.com/signalfx/tracing-examples/tree/main/opentelemetry-tracing/opentelemetry-python-tracing">Examples</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="SECURITY.md">Security</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation">Supported Libraries</a>
    &nbsp;&nbsp;&bull;&nbsp;&nbsp;
    <a href="docs/troubleshooting.md">Troubleshooting</a>
  </strong>
</p>

---
<span class="docs-version-header">The documentation below refers to the in development version of this package. Docs for the latest version ([v0.16.0](https://github.com/signalfx/splunk-otel-python/releases/tag/v0.16.0)) can be found [here](https://github.com/signalfx/splunk-otel-python/blob/v0.16.0/README.md).</span>
---

# Splunk Distribution of OpenTelemetry Python

The Splunk distribution of [OpenTelemetry
Python](https://github.com/open-telemetry/opentelemetry-python) provides
multiple installable packages that automatically instruments your Python
application to capture and report distributed traces to Splunk APM.
Instrumentation works by patching supported libraries at runtime with an
OpenTelemetry-compatible tracer to capture and export trace spans.

This Splunk distribution comes with the following defaults:

- [W3C tracecontext](https://www.w3.org/TR/trace-context/) and [W3C
  baggage](https://www.w3.org/TR/baggage/) context propagation;
  [B3](https://github.com/openzipkin/b3-propagation) can also be
  [configured](docs/advanced-config.md#trace-propagation-configuration).
- [OTLP gRPC
  exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
  configured to send spans to a locally running [Splunk OpenTelemetry
  Connector](https://github.com/signalfx/splunk-otel-collector)
  (`http://localhost:4317`).
- Unlimited default limits for [configuration options](docs/advanced-config.md#trace-configuration) to
  support full-fidelity traces.

If you're currently using the SignalFx Tracing Library for Python and want to
migrate to the Splunk Distribution of OpenTelemetry Python, see [Migrate from
the SignalFx Tracing Library for Python](MIGRATING.md).

> :construction: This project is currently in **BETA**. It is **officially supported** by Splunk. However, breaking changes **MAY** be introduced.

## Requirements

This Splunk Distribution of OpenTelemetry requires Python 3.6 or later.
If you're still using Python 2, continue using the SignalFx Tracing Library
for Python.

## Getting Started

To get started, install the `splunk-opentelemetry[all]` package, run the bootstrap
script and wrap your run command with `splunk-py-trace`.

For example, if the runtime parameters were:

```
python main.py --port=8000
```

Then the runtime parameters should be updated to:

```
$ pip install splunk-opentelemetry[all]
$ splunk-py-trace-bootstrap
$ OTEL_SERVICE_NAME=my-python-app \
    splunk-py-trace python main.py --port=8000
```

To see the Python instrumentation in action with sample applications, see our
[examples](https://github.com/signalfx/tracing-examples/tree/main/opentelemetry-tracing/opentelemetry-python-tracing).

### Basic Configuration

The service name resource attribute is the only configuration option
that needs to be specified. You can set it by adding a `service.name`
attribute as shown in the [example above](#getting-started).

A few other configuration options that may need to be changed or set are:

- Trace propagation format if not sending to other applications using W3C
  trace-context. For example, if other applications are instrumented with
  `signalfx-*-tracing` instrumentation. See the [trace
  propagation](docs/advanced-config.md#trace-propagation-configuration)
  configuration documentation for more information.
- Endpoint if not sending to a locally running Splunk OpenTelemetry Connector
  with default configuration. For example, if the SignalFx Smart Agent is used.
  See the [exporters](docs/advanced-config.md#trace-exporters) configuration
  documentation for more information.
- Environment resource attribute `deployment.environment` to specify what
  environment the span originated from. For example:
  ```
  OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production
  ```
- Service version resource attribute `service.version` to specify the version
  of your instrumented application. For example:
  ```
  OTEL_RESOURCE_ATTRIBUTES=service.version=1.2.3
  ```

The `deployment.environment` and `service.version` resource attributes are not
strictly required, but recommended to be set if they are
available.

The `OTEL_RESOURCE_ATTRIBUTES` syntax is described in detail in the
[trace configuration](docs/advanced-config.md#trace-configuration) section.

### Supported Python Versions

The instrumentation works with Python verion 3.6 and higher. Supported
libraries are listed
[here](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation).

## Advanced Configuration

For the majority of users, the [Getting Started](#getting-started) section is
all you need. Advanced configuration documentation can be found
[here](docs/advanced-config.md). In addition, special cases for instrumentation
are documented [here](docs/instrumentation-special-cases.md).

## Manually instrument an application

Documentation on how to manually instrument a Python application is available
[here](https://opentelemetry-python.readthedocs.io/en/stable/getting-started.html).

To extend the instrumentation with the OpenTelemetry Instrumentation for Python,
you have to use a compatible API version.

The Splunk Distribution of OpenTelemetry Python version <span class="splunk-version">0.16.0</span> is compatible
with:

* OpenTelemetry API version <span class="otel-api-version">1.4.1</span>
* OpenTelemetry SDK version <span class="otel-sdk-version">1.4.1</span>
* OpenTelemetry Instrumentation for Python version <span class="otel-instrumentation-version">0.23b2</span>

## Correlating traces with logs

The Splunk Distribution of OpenTelemetry Python provides a way
to correlate traces with logs. It is enabled automatically as part of the
[logging
instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html).

# License and versioning

The Splunk distribution of OpenTelemetry Python Instrumentation is a
distribution of the [OpenTelemetry Python
project](https://github.com/open-telemetry/opentelemetry-python). It is
released under the terms of the Apache Software License version 2.0. See [the
license file](./LICENSE) for more details.
