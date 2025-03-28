# Release Notes for Splunk OTel Python Version 2

Summary of changes between Splunk OTel Python major versions 1 and 2.

## Overview

Version 2 of the Splunk Distribution of Opentelemetry Python represents a significant rewrite of the distribution,
including a new build system using Hatch, matching the upstream Opentelemetry Python repository. As the upstream
repository has become more mature since Splunk OTel Python 1.0 was released, version 2 has adopted
a smaller footprint, deferring logic and spec compliance to the upstream project, while making vendor-specific features
available for your convenience to send telemetry to Splunk Observability Cloud.

## API

### Version 1

| Function name     | Operation                                                                                 | Arguments                                                                                               |
|-------------------|-------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `start_metrics()` | Configures metrics (sets up meter provider, SystemMetricsInstrumentor, and otlp exporter) | None                                                                                                    |
| `start_tracing()` | Configures tracing (sets up tracer provider, batch span processor, and exporter)          | service_name, span_exporter_factories, access_token, resource_attributes, trace_response_header_enabled |

### Version 2

| Function name        | Operation                              | Arguments |
|----------------------|----------------------------------------|-----------|
| `init_splunk_otel()` | Initializes tracing, metrics, and logs | None      |

## Environment Variables

| Variable                                         | Default   | Description                                                                                          |
|--------------------------------------------------|-----------|------------------------------------------------------------------------------------------------------|
| SPLUNK_ACCESS_TOKEN                              |           | Adds token to requests to enable direct ingest (for skipping the Collector)                          |
| SPLUNK_REALM                                     |           | Sets the metrics and traces endpoints by realm (e.g. `us1`) and sets the protocol to `http/protobuf` |
| SPLUNK_PROFILER_ENABLED                          | false     | Configures the Splunk profiler to start polling at startup                                           |
| SPLUNK_TRACE_RESPONSE_HEADER_ENABLED             | true      | Configures injection of tracecontext headers into HTTP responses if true                             |
| SPLUNK_PROFILER_CALL_STACK_INTERVAL              | 1000      | Sets the profiler poll interval, in milliseconds                                                     |
| SPLUNK_PROFILER_LOGS_ENDPOINT                    |           | Sets the OTel logging endpoint, only if profiler is enabled                                          |
| OTEL_METRICS_EXPORTER                            | otlp      | Sets the metrics exporter                                                                            |
| OTEL_TRACES_EXPORTER                             | otlp      | Sets the traces exporter                                                                             |
| OTEL_LOGS_EXPORTER                               | otlp      | Sets the logs exporter                                                                               |
| OTEL_EXPERIMENTAL_RESOURCE_DETECTORS             | host      | Configures a host resource detector to set telemetry attributes                                      |
| OTEL_TRACES_SAMPLER                              | always_on | Configures the sampler to export all traces                                                          |
| OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED | true      | Exports all logs                                                                                     |
| OTEL_SPAN_LINK_COUNT_LIMIT                       | 1000      | Sets the maximum allowed span link count                                                             |
| OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT                | 12000     | Sets the maximum allowed attribute value size                                                        |
| OTEL_ATTRIBUTE_COUNT_LIMIT                       | _empty_   |                                                                                                      |
| OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT                  | _empty_   |                                                                                                      |
| OTEL_SPAN_EVENT_COUNT_LIMIT                      | _empty_   |                                                                                                      |
| OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT                 | _empty_   |                                                                                                      |
| OTEL_LINK_ATTRIBUTE_COUNT_LIMIT                  | _empty_   |                                                                                                      |

## Environment Variable Changes Between 1.x and 2.x

| Variable                             | Changes in 2.x                                                                  |
|--------------------------------------|---------------------------------------------------------------------------------|
| OTEL_METRICS_ENABLED                 | Removed (set `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=system_metrics` to disable) |
| OTEL_METRICS_EXPORTER                | Overridden in 1.x, configurable in 2.x                                          |
| OTEL_TRACE_ENABLED                   | Removed (defaulted to `true`)                                                   |
| OTEL_PYTHON_LOG_CORRELATION          | No longer set (previously reformatted logs, adding trace IDs)                   |
| OTEL_METRICS_EXPORTER                | Added                                                                           |
| OTEL_LOGS_EXPORTER                   | Added                                                                           |
| OTEL_EXPERIMENTAL_RESOURCE_DETECTORS | Added                                                                           |
| OTEL_TRACES_SAMPLER                  | Added (previously defaulted to `parentbased_always_on`)                         |

## Auto-instrumentation

Version 1 of Splunk OTel Python supplied a script to run a python application with OTel auto instrumentation. For
example:

`$ splunk-py-trace python myapp.py`

In version 2 of Splunk OTel Python, the `splunk-py-trace` command is replaced by `opentelemetry-instrument`, the same
command supplied by the core OpenTelemetry Python project.

| Version | Commands                           |
|---------|------------------------------------|
| 1.x     | `splunk-py-trace`, `splk-py-trace` |
| 2.x     | `opentelemetry-instrument`         |

## Bootstrap Script

Version 1 of Splunk OTel Python supplied a script to install instrumentation libraries based on the packages
already installed in the current environment. In version 2 the `splunk-py-trace-bootstrap` command is replaced by
`opentelemetry-bootstrap`, the same command supplied by the core OpenTelemetry Python project.

| Version | Commands                                               |
|---------|--------------------------------------------------------|
| 1.x     | `splunk-py-trace-bootstrap`, `splk-py-trace-bootstrap` |
| 2.x     | `opentelemetry-bootstrap`                              |

> **Note:** `opentelemetry-bootstrap` does not install packages automatically. You need to pass it the `-a install`
> flag to install them.
