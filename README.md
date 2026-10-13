# Splunk Distribution of OpenTelemetry Python

[![PyPI - Version](https://img.shields.io/pypi/v/splunk-opentelemetry.svg)](https://pypi.org/project/splunk-opentelemetry)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/splunk-opentelemetry.svg)](https://pypi.org/project/splunk-opentelemetry)

The Splunk Distribution of OpenTelemetry Python extends
[OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python) to automatically instrument Python
applications and export traces, metrics, and logs to Splunk Observability Cloud. It patches supported libraries at
runtime with OpenTelemetry-compatible instrumentation and provides Splunk-specific configuration defaults.

This distribution comes with the following defaults:

- [OTLP gRPC exporters](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
  configured to send traces, metrics, and logs to a locally running
  [Splunk OpenTelemetry Collector](https://github.com/signalfx/splunk-otel-collector)
  (`http://localhost:4317`).
- Unlimited default limits for
  [configuration options](https://docs.splunk.com/Observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html)
  to support full-fidelity traces.
- [System metrics instrumentation](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation/opentelemetry-instrumentation-system-metrics).
- Python logging instrumentation.

## Requirements

The Splunk Distribution of OpenTelemetry Python requires Python 3.10 or later. Supported
libraries are listed
[here](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation).

## Get started

For complete instructions on how to get started with the Splunk Distribution of OpenTelemetry Python, see
[Instrument a Python application for Splunk Observability Cloud](https://quickdraw.splunk.com/redirect/?product=Observability&version=current&location=python.application) in the official documentation.

For the standard OpenTelemetry setup, install the Splunk Distribution of OpenTelemetry Python in your application
environment. The distribution configures OTLP exporters for traces, metrics, and logs, includes system metrics
instrumentation, and enables Python logging instrumentation.

```bash
pip install splunk-opentelemetry
```

Install instrumentation packages for the libraries your application uses:

```bash
opentelemetry-bootstrap -a install
```

Then run your application with `opentelemetry-instrument`:

```bash
OTEL_SERVICE_NAME=my-python-service opentelemetry-instrument python app.py
```

### Experimental PostgreSQL trace correlation

Set `SPLUNK_POSTGRESQL_TRACE_CONTEXT_PROPAGATION_ENABLED=true` to place each
instrumented psycopg or psycopg2 database span's W3C `traceparent` in
PostgreSQL's `application_name` immediately before the query. This sends one
additional `SET application_name` command per traced query.
The feature targets Psycopg 3 synchronous and asynchronous connections and
Psycopg2 synchronous connections. Psycopg2 asynchronous connections pass through
without trace propagation.

This opt-in replaces the connection's `application_name` and leaves the value
set after the query. If instrumentation creates no valid new database span, the
feature resets the setting to the connection's configured default. It does not
restore a value that the application previously set through SQL. Queries that
bypass instrumentation, including suppressed queries and cursors created before
instrumentation, can inherit an earlier query's trace context.
Psycopg 3 named cursors use a separate server-cursor factory that the current
upstream instrumentor does not wrap. Those queries, cursor fetch operations,
and COPY operations are outside this feature's automatic coverage.

The feature logs internal command failures and attempts the customer query. A
failed command can leave a transaction aborted, so the customer query can also
fail. The feature does not roll back application transactions. Database span
duration and database operation duration metrics include lock waiting and the
additional command.

Manual instrumentation must initialize the Splunk distro first with
`init_splunk_otel()`, or call `enable_postgresql_trace_context_propagation()`
before using `PsycopgInstrumentor` or `Psycopg2Instrumentor`.

Install the corresponding OpenTelemetry driver instrumentation package. The
environment switch applies when `OTEL_CONFIG_FILE` is unset. Activation lasts
for the process lifetime. To turn it off, unset the switch and restart. Only
queries using the instrumented driver participate in its connection lock.

By default, OTLP exporters send telemetry to a locally running
[Splunk OpenTelemetry Collector](https://github.com/signalfx/splunk-otel-collector)
at `http://localhost:4317`. To send telemetry directly to Splunk Observability
Cloud instead, set `SPLUNK_REALM` and `SPLUNK_ACCESS_TOKEN` before starting your
application. `SPLUNK_REALM` configures direct ingest endpoints for traces and
metrics.

## Declarative configuration

The distribution includes experimental support for the OpenTelemetry declarative
configuration file format. Set `OTEL_CONFIG_FILE` to the path of the YAML
configuration file when you start the instrumented application:

```bash
OTEL_CONFIG_FILE=/path/to/config.yaml opentelemetry-instrument python app.py
```

See the [basic declarative configuration example](docs/examples/declarative-config.yaml),
which exports traces, metrics, and logs to a local Collector at `http://localhost:4317`.

This support configures upstream OpenTelemetry SDK components. The GDI
`distribution.splunk` configuration block is not supported yet. Configure
exporters, including their endpoints and authentication headers, in the YAML file.
OpAMP does not report the declarative file as effective configuration and cannot
manage it remotely yet.

## Profiling

The Splunk Distribution of OpenTelemetry Python supports continuous profiling and
call graph profiling. Both modes export profiling data through OpenTelemetry logs
for correlation with traces in Splunk APM. See [Profiling](docs/profiling.md) for
configuration and limitations.

## Optional: Cisco SecureApp

To also install the [Cisco SecureApp](https://pypi.org/project/secureapp-python-agent/)
OpenTelemetry extension, specify the `secureapp` extra:

```bash
pip install "splunk-opentelemetry[secureapp]"
```

This extra installs the SecureApp Python agent, which reports runtime Python
package dependencies through OpenTelemetry logs.

SecureApp dependency logs use the `secureapp` instrumentation scope. Collector
deployments must route those logs to the SecureApp event ingest endpoint
(`/v3/event`) and add the SecureApp instrumentation header on the outbound
exporter. See [docs/secureapp.md](docs/secureapp.md) for setup details and
[docs/examples/secureapp-collector-config.yaml](docs/examples/secureapp-collector-config.yaml)
for a collector example.

## Fleet management with OpAMP

The Splunk Distribution of OpenTelemetry Python provides OpAMP support. When enabled, the OpAMP client connects to the
configured endpoint and reports the Python agent's status and settings. Agents connected to Splunk Observability Cloud
appear on the Fleet Management page.

Set `SPLUNK_OPAMP_ENABLED=true` to enable OpAMP. The default OpAMP endpoint is a local Splunk OpenTelemetry Collector.
See [OpAMP](docs/opamp.md) for setup, configuration, and limits.

## License

The Splunk Distribution of OpenTelemetry Python is a distribution of
[OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python). It is licensed under the terms of the
Apache Software License version 2.0. See [the license file](./LICENSE.txt) for more details.
