> The official Splunk documentation for this page is [Configure the Python agent](https://docs.signalfx.com/en/observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html#trace-exporters-settings-python). For instructions on how to contribute to the docs, see [CONTRIBUTE.md](../CONTRIBUTE.md).

# Exporting telemetry data

This package can export spans in the OTLP format over gRPRC or Jaeger Thrift
format over HTTP. This allows you to export data to wide range of destinations
such as OpenTelemetry Collector, SignalFx Smart Agent or even Splunk APM
ingest.

## To Splunk OpenTelemetry Connector

This is the default option. You do not need to set any config options if you
want to exporter to the OpenTelemetry collector, the collector has OTLP gRPC
receiver enabled with default settings and can be reached by `localhost` as by
default everything by be exported to `http://localhost:4317` in OTLP over gRPC.

If your collector cannot be reached at `http://localhost:4317`, you'll need to
set the `OTEL_EXPORTER_OTLP_ENDPOINT` to
`http://<otel-collector-address>:<port>`. Replace `<otel-collector-address>`
and `<port>` with the address and port of your OpenTelemetry Collector
deployment.

Note: You'll make sure that the OTLP gRPC exporter is installed. This can be
done by running `pip install splunk-opentelemetry[all]` or
`splunk-opentelemetry[otlp]`.

## To SignalFx Smart Agent

1. Set `OTEL_TRACES_EXPORTER` environment variable to `jaeger-thrift-splunk`.
   If you are running the SignalFx Smart Agent locally (reachable via
   `localhost`) and it is listening on the default port (`9080`), you do not
   need to perform any additional steps. Otherwise, follow the next step. 
2. Set the `OTEL_EXPORTER_JAEGER_ENDPOINT` environment variable to
   `http://<address>:<port>/v1/trace`. Replace `<address>` and `<port>` with
   the address and port of your Smart Agent deployment.

Note: You'll make sure that the Jaeger Thrift exporter is installed. This can
be done by running `pip install splunk-opentelemetry[all]` or
`splunk-opentelemetry[jaeger]`.

## To Splunk Observability Cloud

In order to send traces directly to SignalFx ingest API, you need to:

1. Set `OTEL_TRACES_EXPORTER` to `jaeger-thrift-splunk`.
2. Set `OTEL_EXPORTER_JAEGER_ENDPOINT` to
   `https://ingest.<realm>.signalfx.com/v2/trace` where `realm` is your
   SignalFx realm e.g, `https://ingest.us0.signalfx.com/v2/trace`.
3. Set `SPLUNK_ACCESS_TOKEN` to one of your Splunk APM access tokens.

Note: You'll make sure that the Jaeger Thrift exporter is installed. This can
be done by running `pip install splunk-opentelemetry[all]` or
`splunk-opentelemetry[jaeger]`.

## Using a different exporter

The `splunk-opentelemetry` Python package does not install any exporters by
default. You can install it with the OTLP or Jaeger Thrift exporter by using
the `otlp` or `jaeger` extra options. For example, installing
`splunk-opentelemetry[otlp]` will also pull in the OTLP gRPC exporter.
Similarly, installing `splunk-opentelemetry[jaeger]` will install the Jaeger
Thrift exporter. You can also install both exporters by mentioning them both
like `splunk-opentelemetry[jaeger,otlp]`

The distributions uses OTLP by default so we recommend installing
`splunk-opentelemetry[otlp]` unless you want to use another exporter.

Once you install the exporter package you want to use, you can tell the
distribution to use a different exporter by setting the `OTEL_TRACES_EXPORTER`
environment variables.

For example, to use the Jaeger exporter, set it as follows:

```
OTEL_TRACES_EXPORTER=jaeger-thrift-splunk
```

### Using multiple exporters

The environment variable accepts multiple comma-separated values. If multiple
exporters are specified, all of them will be used. This can be used to export
to multiple destinations or to debug with the console exporter while still
exporting to another destination. For example, the following configuration will
export all spans using both the OTLP exporter and the Console exporter.

```
OTEL_TRACES_EXPORTER=otlp,console_span
```

### Accepted values for OTEL_TRACES_EXPORTER

This package uses Python's entry points mechanism to look up the requested
exporters. As a result, you can install any thrid party or custom exporter
package and as long as it specifies a `opentelemetry_exporter` entry point to
the exporter implementation, you can specify it as a value in
`OTEL_TRACES_EXPORTER`.

Known values and the Python packages they ship in are listed below.

| Exporter name        | Python package                         | Additional comments                                              |
| -------------        | ---------------                        | ---------------------                                            |
| otlp                 | opentelemetry-exporter-otlp-proto-grpc | Can be installed with `pip install splunk-opentelemetry[otlp]`   |
| jaeger-thrift-splunk | opentelemetry-exporter-jaeger-thrift   | Can be installed with `pip install splunk-opentelemetry[jaeger]` |
| console_span         | opentelemetry-sdk                      | Always installed with `splunk-opentelemetry`                     |
