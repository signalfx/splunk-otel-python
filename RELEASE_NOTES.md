# Release Notes for Splunk OTel Python Version 2

Summary of changes between Splunk OTel Python major versions 1 and 2.

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

| Variable                              | v2 default | v1 -> v2 changes                                               | Description                                                                                                        |
|---------------------------------------|------------|----------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------|
| SPLUNK_ACCESS_TOKEN                   |            | None                                                           | Adds token to requests to enable direct ingest (for skipping the collector)                                        |
| OTEL_METRICS_ENABLED                  | true       | None                                                           | Causes metrics to be configured (with an otlp-grpc metric exporter and a SystemMetricInstrumentor)                 |
| OTEL_METRICS_EXPORTER                 | otlp       | Hard coded in v1, configurable in v2                           | Indicates the metrics exporter                                                                                     |
| OTEL_TRACE_ENABLED                    | true       | None                                                           | Causes tracing to be configured and instrumentors loaded                                                           |
| OTEL_TRACES_EXPORTER                  | otlp       | None                                                           | Indicates the traces exporter                                                                                      |
| OTEL_PYTHON_DISABLED_INSTRUMENTATIONS |            | None                                                           | Disables instrumentations by entrypoint name                                                                       |
| SPLUNK_PROFILER_ENABLED               | false      | None                                                           | Causes the Splunk profiler to start polling at startup                                                             |
| OTEL_SPAN_LINK_COUNT_LIMIT            | 1000       | None                                                           | Sets the maximum allowed span link count                                                                           |
| OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT     | 12000      | None                                                           | Sets the maximum allowed attribute value size                                                                      |
| SPLUNK_TRACE_RESPONSE_HEADER_ENABLED  | true       | None                                                           | Causes a ServerTimingReponsePropagator to be configured if true (injects tracecontext headers into HTTP responses) |
| OTEL_EXPERIMENTAL_RESOURCE_DETECTORS  | host       | Not set in v1                                                  | Causes a host resource detector to be configured to set telemetry attributes                                       |
| OTEL_TRACES_SAMPLER                   | always_on  | Not set in v1 (took upstream default of parentbased_always_on) |                                                                                                                    |

## Auto-instrumentation

Version 1 of Splunk OTel Python supplied a script to run a python application with OTel auto instrumentation. For
example:

`$ splunk-py-trace python myapp.apy`

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
