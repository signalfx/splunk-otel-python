# Advanced Configuration

## Splunk distribution configuration

| Environment variable                   | Config Option                   | Default value | Support     | Description                                                                                                                                                                                                      |
| -------------------------------------- | ------------------------------- | ------------  | ----------- | ---                                                                                                                                                                                                              |
| `SPLUNK_ACCESS_TOKEN`                  | `access_token`                  | unset         | Stable      | (Optional) Auth token allowing exporters to communicate directly with the Splunk cloud, passed as `X-SF-TOKEN` header. Currently, the [Jaeger and OTLP trace exporters](#trace-exporters) support this property.
| `SPLUNK_TRACE_RESPONSE_HEADER_ENABLED` | `trace_response_header_enabled` | True          | Experimental | Enables adding server trace information to HTTP response headers.

## Trace exporters

| Environment variable              | Config Option         | Default value                    | Support     | Description                                                                                                                              |
| --------------------------------- | --------------------- | -------                          | ----------- | ---                                                                                                                                      |
| `OTEL_EXPORTER_OTLP_ENDPOINT`     |                       | `http://localhost:4317`          | Stable      | The OTLP endpoint to connect to.
| `OTEL_EXPORTER_JAEGER_ENDPOINT`   |                       | `http://localhost:9080/v1/trace` | Stable      | The Jaeger endpoint to connect to.
| `OTEL_TRACES_EXPORTER`            | `exporter_factories`  | `otlp`                           | Stable      | Select the traces exporter to use. We recommend using either the OTLP exporter (`otlp`) or the Jaeger exporter (`jaeger-thrift-splunk`).

The Splunk Distribution of OpenTelemetry Python uses the OTLP traces exporter as the default setting. Please note that the
OTLP format is neither supported by Splunk Observability Cloud ingest API nor by the (now deprecated) [SignalFx Smart Agent](https://github.com/signalfx/signalfx-agent).
If you wish to use the Jaeger exporter instead, you can set it by using the `OTEL_TRACES_EXPORTER` environment variable.

For example:

```bash
export OTEL_TRACES_EXPORTER=jaeger-thrift-splunk
```

### Exporting directly to Splunk Observability Cloud

Only Splunk Jaeger exporter can be configured to export traces directly to Splunk Observability Cloud. To achieve that, you need
to set the `SPLUNK_ACCESS_TOKEN`, `OTEL_TRACE_EXPORTERS` and `OTEL_EXPORTER_JAEGER_ENDPOINT` environment vairables.

For example:

```bash
export SPLUNK_ACCESS_TOKEN=my_splunk_token
export OTEL_TRACES_EXPORTER=jaeger-thrift-splunk
export OTEL_EXPORTER_JAEGER_ENDPOINT=https://ingest.us0.signalfx.com/v2/trace
```

More information about exporting can be found [here](exporting-data.md).

## Trace propagation configuration

| Environment variable | Default value          | Support | Description                                                                                                                    |
| -------------------- | ---------------------- | ------- | -----------                                                                                                                    |
| `OTEL_PROPAGATORS`   | `tracecontext,baggage` | Stable  | Comma-separated list of propagator names to be used. See [Configuring Propagators](#configuring-propagators) for more details.

If you wish to be compatible with older versions of the Splunk Distribution of OpenTelemetry Python (or SignalFx
Python Tracing) you can set the trace propagator to B3:

```bash
export OTEL_PROPAGATORS=b3multi
```

More information about trace propagation can be found [here](configuring-propagators.md).

## Trace configuration

| Environment variable      | Config Option         | Default value             | Notes                                                                                                                                                                                                         |
| ------------------------- | --------------------- | ------------------------- | ----------------------------------------------------------------------                                                                                                                                        |
| OTEL_SERVICE_NAME                 | service_name          | `unnamed-python-service`  | The service name of this Python application. |
| OTEL_RESOURCE_ATTRIBUTES          | resource_attributes   | unset                     | Comma-separated list of resource attributes added to every reported span. <details><summary>Example</summary>`service.name=my-python-service,service.version=3.1,deployment.environment=production`</details> |
| OTEL_TRACE_ENABLED                |                       | `true`                    | Globally enables tracer creation and auto-instrumentation.  |
| OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT   |                       | `""` (unlimited)          | Maximum number of attributes per span.  |
| OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT  |                       | `""` (unlimited)          | Maximum number of attributes per event.  |
| OTEL_LINK_ATTRIBUTE_COUNT_LIMIT   |                       | `""` (unlimited)          | Maximum number of attributes per link.  |
| OTEL_SPAN_EVENT_COUNT_LIMIT       |                       | `""` (unlimited)          | Maximum number of events per span. |
| OTEL_SPAN_LINK_COUNT_LIMIT        |                       | `1000`                    | Maximum number of links per span. |
| OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT |                       | `1200`                    | Maximum length string attribute values can have. Values larger than this will be truncated. |

## Instrument and configure with code

If you cannot use `splunk-py-trace` command, you can also add a couple of lines
of code to your Python application to achieve the same result.

```python
from splunk_otel.tracing import start_tracing

start_tracing()

# Also accepts optional config options:
# start_tracing(
#   service_name='my-python-service',
#   span_exporter_factories=[OTLPSpanExporter]
#   access_token='',
#   max_attr_length=1200,
#   trace_response_header_enabled=True,
#   resource_attributes={
#    'service.version': '3.1',
#    'deployment.environment': 'production',
#  })

# rest of your python application's entrypoint script
```

## Other

- Advanced installation information can be found [here](advanced-install.md)
- Instrumentation special cases information can be found [here](instrumentation-special-cases.md)
