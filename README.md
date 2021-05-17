
# Splunk distribution of OpenTelemetry Python

[![OpenTelemetry Python Version](https://img.shields.io/badge/otel-1.2.0-blueviolet?style=for-the-badge)](https://github.com/open-telemetry/opentelemetry-python/releases/tag/v1.2.0)
[![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/signalfx/splunk-otel-python?style=for-the-badge)](https://github.com/signalfx/splunk-otel-python/releases)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/splunk-opentelemetry?style=for-the-badge)](https://pypi.org/project/splunk-opentelemetry/)
[![CircleCI](https://img.shields.io/circleci/build/github/signalfx/splunk-otel-python/main?style=for-the-badge)](https://circleci.com/gh/signalfx/splunk-otel-python)
[![Codecov](https://img.shields.io/codecov/c/github/signalfx/splunk-otel-python?style=for-the-badge&token=XKXjEQKGaK)](https://codecov.io/gh/signalfx/splunk-otel-python)

-------

The documentation below refers to the in development version of this package. Docs for the latest version ([v0.13.0](https://github.com/signalfx/splunk-otel-python/releases/tag/v0.13.0)) can be found [here](https://github.com/signalfx/splunk-otel-python/blob/v0.13.0/README.md).

-------

The Splunk distribution of [OpenTelemetry
Python](https://github.com/open-telemetry/opentelemetry-python) provides
multiple installable packages that automatically instruments your Python
application to capture and report distributed traces to Splunk APM.

This Splunk distribution comes with the following defaults:

- [W3C tracecontext](https://www.w3.org/TR/trace-context/) and [W3C baggage](https://www.w3.org/TR/baggage/) context propagation.
- [OTLP gRPC exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
  configured to send spans to a locally running [OpenTelemetry Collector](https://docs.signalfx.com/en/latest/apm/apm-getting-started/apm-opentelemetry-collector.html)
  (`http://localhost:4317`).
- Unlimited default limits for [configuration options](#trace-configuration) to
  support full-fidelity traces.

If you're currently using the SignalFx Tracing Library for Python and want to
migrate to the Splunk Distribution of OpenTelemetry Python, see [Migrate from
the SignalFx Tracing Library for Python](migration.md).

> :construction: This project is currently in **BETA**. It is **officially supported** by Splunk. However, breaking changes **MAY** be introduced.

## Requirements

This Splunk Distribution of OpenTelemetry requires Python 3.6 or later.
If you're still using Python 2, continue using the SignalFx Tracing Library
for Python.

## Getting Started

The instrumentation works with Python version 3.6+. Supported libraries are
listed
[here](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/master/instrumentation).

To get started, install the `splunk-opentelemetry[all]` package, run the bootstrap
script and wrap your run command with `splk-py-trace`.

For example, if the runtime parameters were:

```
python main.py --port=8000
```

Then the runtime parameters should be updated to:

```
$ pip install splunk-opentelemetry[all]
$ splk-py-trace-bootstrap
$ OTEL_SERVICE_NAME=my-python-app \
    splk-py-trace python main.py --port=8000
```


The service name is the only configuration option that typically needs to be
specified. A couple other configuration options that may need to be changed or
set are:

- Endpoint if not sending to a locally running OpenTelemetry Collector.
- Environment attribute (example:
  `OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production`) to specify what
  environment the span originated from.

Instrumentation works by patching supported libraries at runtime with an
OpenTelemetry-compatible tracer to capture and export trace spans. 

To see the Python instrumentation in action with sample applications, see our
[examples](https://github.com/signalfx/tracing-examples/tree/main/opentelemetry-tracing/opentelemetry-python-tracing).

## All configuration options

| Environment variable          | Config Option                        | Default value                        | Notes                                                                  |
| ----------------------------- | ------------------------------------ | ------------------------------------ | ---------------------------------------------------------------------- |
| OTEL_SERVICE_NAME             | service_name                         | `unnamed-python-service`     | The service name of this Python application.   |
| OTEL_TRACES_EXPORTER | exporter_factories | `otlp`     | The exporter(s) that should be used to export tracing data. |
| OTEL_EXPORTER_OTLP_ENDPOINT |  | `http://localhost:4317`     | The OTLP gRPC endpoint to connect to. Used when `OTEL_TRACES_EXPORTER` is set to `otlp` |
| OTEL_EXPORTER_JAEGER_ENDPOINT |  | `http://localhost:9080/v1/trace`     | The Jaeger Thrift endpoint to connect to. Used when `OTEL_TRACES_EXPORTER` is set to `jaeger-thrift-splunk` |
| SPLUNK_ACCESS_TOKEN          | access_token |      | The optional organization access token for trace submission requests.  |
| SPLUNK_MAX_ATTR_LENGTH       | max_attr_length | `1200`            | Maximum length of string attribute value in characters. Longer values are truncated.                                                                                                                                                                                                                                                                                                                      |
| SPLUNK_TRACE_RESPONSE_HEADER_ENABLED | trace_response_header_enabled | True | Enables adding server trace information to HTTP response headers. |
| OTEL_RESOURCE_ATTRIBUTES      | resource_attributes | unset          | Comma-separated list of resource attributes added to every reported span. <details><summary>Example</summary>`service.name=my-python-service,service.version=3.1,deployment.environment=production`</details>
| OTEL_PROPAGATORS              |            | `tracecontext,baggage`   | Comma-separated list of propagator names to be used. See[Configuring Propagators](#configuring-propagators) for more details.
| OTEL_TRACE_ENABLED            |            | `true`         | Globally enables tracer creation and auto-instrumentation. |


## Exporting telemetry data

This package can export spans in the OTLP format over gRPRC or Jaeger Thrift format over HTTP.
This allows you to export data to wide range of destinations such as OpenTelemetry Collector,
SignalFx Smart Agent or even Splunk APM ingest. 

### To OpenTelemetry Collector

This is the default option. You do not need to set any config options if you want to exporter
to the OpenTelemetry collector, the collector has OTLP gRPC receiver enabled with default settings
and can be reached by `localhost` as by default everything by be exported to `http://localhost:4317`
in OTLP over gRPC.

If your collector cannot be reached at `http://localhost:4317`, you'll need to set the `OTEL_EXPORTER_OTLP_ENDPOINT`
to `http://<otel-collector-address>:<port>`. Replace `<otel-collector-address>` and `<port>` with the address and
port of your OpenTelemetry Collector deployment.

Note: You'll make sure that the OTLP gRPC exporter is installed. This can be done by running `pip install splunk-opentelemetry[all]`
or `splunk-opentelemetry[otlp]`.

### To SignalFx Smart Agent

1. Set `OTEL_TRACES_EXPORTER` environment variable to `jaeger-thrift-splunk`.
   If you are running the SignalFx Smart Agent locally (reachable via `localhost`) and it is listening 
on the default port (`9080`), you do not need to perform any additional steps. Otherwise, follow the next step. 
2. Set the `OTEL_EXPORTER_JAEGER_ENDPOINT` environment variable to `http://<address>:<port>/v1/trace`. Replace `<address>` and `<port>`
with the address and port of your Smart Agent deployment.

Note: You'll make sure that the Jaeger Thrift exporter is installed. This can be done by running `pip install splunk-opentelemetry[all]`
or `splunk-opentelemetry[jaeger]`.

### To Splunk Observability Cloud

In order to send traces directly to SignalFx ingest API, you need to:

1. Set `OTEL_TRACES_EXPORTER` to `jaeger-thrift-splunk`.
2. Set `OTEL_EXPORTER_JAEGER_ENDPOINT` to
   `https://ingest.<realm>.signalfx.com/v2/trace` where `realm` is your
   SignalFx realm e.g, `https://ingest.us0.signalfx.com/v2/trace`.
3. Set `SPLUNK_ACCESS_TOKEN` to one of your Splunk APM access tokens.

Note: You'll make sure that the Jaeger Thrift exporter is installed. This can be done by running `pip install splunk-opentelemetry[all]`
or `splunk-opentelemetry[jaeger]`.

## Configuring Propagators <a name="configuring-propagators"></a>

This package uses W3C trace context and W3C baggage propagators by default. You can override
this by setting the `OTEL_PROPAGATORS` environment variable to a comma separated list of one
more propagators. The SDK will use Python's entry points mechanism to load the specified
propagator implementation(s) and use it.

For example, to only use W3C trace context without baggage, you can set the environment variable
`OTEL_PROPAGATORS` environment variable to `tracecontext`.

You can specify any propagator name as long as the propagator implementation can be found via
entry points by that name.

### Configuring B3 propagator


If you'd like to use `b3` instead of or in addition to the default propagators, you can set `OTEL_PROPAGATORS` to `b3`
for [B3 single header](https://github.com/openzipkin/b3-propagation#single-header) or `b3multi` for
[B3 multi header](https://github.com/openzipkin/b3-propagation#multiple-headers) implementation. For example, to configure
your service to use B3 multi header and W3C baggage, set the environment variable as

```
OTEL_PROPAGATORS=b3multi,baggage
```

You can specify any combination of supported propagators. Choices are `tracecontext`, `baggae`, `b3` and `b3multi`. Note that
`b3` and `b3multi` are only available when the `opentelemetry-propagator-b3` package is installed. This is installed automatically
by installing `splunk-opentelemetry[all]` or `splunk-opentelemetry[b3]`.


## Advanced Getting Started

### Instrument and configure with code

If you cannot use `splk-py-trace` command, you can also add a couple of lines
of code to your Python application to achieve the same result.

```python
from splunk_otel.tracing import start_tracing

start_tracing()

# Also accepts optional config options:
# start_tracing(
#   service_name='my-python-service',
#   exporter_factories=[OTLPSpanExporter]
#   access_token='',
#   max_attr_length=1200,
#   trace_response_header_enabled=True,
#   resource_attributes={
#    'service.version': '3.1',
#    'deployment.environment': 'production',
#  })

# rest of your python application's entrypoint script
```

### Using a different exporter

The `splunk-opentelemetry` Python package does not install any exporters by default. You can install it with the OTLP or Jaeger Thrift exporter by
using the `otlp` or `jaeger` extra options. For example, installing `splunk-opentelemetry[otlp]` will also pull in the OTLP gRPC exporter. Similarly,
installing `splunk-opentelemetry[jaeger]` will install the Jaeger Thrift exporter. You can also install both exporters by mentioning them
both like `splunk-opentelemetry[jaeger,otlp]`

The distributions uses OTLP by default so we recommend installing `splunk-opentelemetry[otlp]` unless you want to use another exporter.

Once you install the exporter package you want to use, you can tell the distribution to use a different exporter by setting the `OTEL_TRACES_EXPORTER`
environment variables.

For example, to use the Jaeger exporter, set it as follows:

```
OTEL_TRACES_EXPORTER=jaeger-thrift-splunk
```

#### Using multiple exporters

The environment variable accepts multiple comma-separated values. If multiple exporters are specified, all of them will be used. This can be used to export
to multiple destinations or to debug with the console exporter while still exporting to another destination. For example, the following configuration will
export all spans using both the OTLP exporter and the Console exporter.

```
OTEL_TRACES_EXPORTER=otlp,console_span
```

#### Accepted values for OTEL_TRACES_EXPORTER

This package uses Python's entry points mechanism to look up the requested exporters. As a result, you can install any thrid party or custom exporter package and
as long as it specifies a `opentelemetry_exporter` entry point to the exporter implementation, you can specify it as a value in `OTEL_TRACES_EXPORTER`.

Known values and the Python packages they ship in are listed below


| Exporter name | Python package | Additional comments |
| ------------- | --------------- | --------------------- | 
| otlp | opentelemetry-exporter-otlp-proto-grpc | Can be installed with `pip install splunk-opentelemetry[otlp]` | 
| jaeger-thrift-splunk | opentelemetry-exporter-jaeger-thrift  | Can be installed with `pip install splunk-opentelemetry[jaeger]` | 
| console_span | opentelemetry-sdk | Always installed with `splunk-opentelemetry` | 


### Bootstrap: List requirements instead of installing them

The `splk-py-trace-bootstrap` command can optionally print out the list of
packages it would install if you chose. In order to do so, pass
`-a=requirements` CLI argument to it. For example,

```
splk-py-trace-bootstrap -a requirements
```

Will output something like the following:

```
opentelemetry-instrumentation-falcon>=0.15b0
opentelemetry-instrumentation-jinja2>=0.15b0
opentelemetry-instrumentation-requests>=0.15b0
opentelemetry-instrumentation-sqlite3>=0.15b0
```

You can pipe the output of this command to append the new packages to your
requirements.txt file or to something like `poetry add`.


### Installing only a subset of dependencies

Installing `splunk-opentelemetry[all]` automatically pulls in all of the optional dependencies. These include the OTLP gRPC exporter, the Jaeger Thrift exporter
and the B3 propagator. If you'd like to install only the packages you need, you can use any combination of `oltp`, `jaeger` and `b3`. For example, in order
to install only `otlp` exporter, you can run

```
pip install splunk-opentelemetry[otlp]
```

To install the Jaeger Thrift exporter and the B3 propagator, you can run

```
pip install splunk-opentelemetry[jaeger,b3]
```

## Special Cases

### Celery

Tracing Celery workers works out of the box when you use the `splk-py-trace`
command to start your Python application. However, if you are instrumenting
your celery workers with code, you'll need to make sure you setup tracing for
each worker by using Celery's `celery.signals.worker_process_init` signal.

For example:

```python
from splunk_otel.tracing import start_tracing
from celery.signals import worker_process_init

@worker_process_init.connect(weak=False)
def on_worker_process_init(*args, **kwargs):
    start_tracing()

# rest of your python application's entrypoint script
```

### Django

Automatically instrumenting Django requires `DJANGO_SETTINGS_MODULE`
environment variable to be set. The value should be the same as set in your
`manage.py` or `wsgi.py` modules. For example, if your manage.py file sets this
environment variable to `mydjangoproject.settings` and you start your Django
project as `./manage.py runserver`, then you can automatically instrument your
Django project as follows:

```
export DJANGO_SETTINGS_MODULE=mydjangoproject.settings
splk-py-trace ./manage.py runserver
```

### Gunicorn

Like Celery, we'll also need to setup tracing per Gunicorn worker. This can be
done by setting up tracing inside Gunicorn's `post_fork()` handler.

For example:

```python
# gunicorn.config.py
from splunk_otel.tracing import start_tracing

def post_fork(server, worker):
    start_tracing()
```

Then add `-c gunicorn.config.py` CLI flag to your gunicorn command.

### UWSGI 

When using UWSGI, tracing must be setup as a response to the `post_fork` signal. 

For example:

```python
import uwsgidecorators
from splunk_otel.tracing import start_tracing

@uwsgidecorators.postfork
def setup_tracing():
    start_tracing()

```

##### Running with uwsgi
```
uwsgi --http :9090 --wsgi-file <your_app.py> --callable <your_wsgi_callable> --master --enable-threads
```

The above snippet should be placed in the main python script that uwsgi imports and loads.

#### UWSGI and Flask

Using USWGI with Flask requires one additional little step. Calling `start_tracing()` does not auto-instrument pre-existing flask app instances but only flask instances created after. When running flask with uwsgi, we need to create a new flask app instance before the post_fork signal is emitted. This means your flask app will not be auto-instrumented. However, you can still auto-instrument an existing flask app explicitly by importing and calling the flask instrumentor. 

For example:
```python
# app.py
import uwsgidecorators
from splunk_otel.tracing import start_tracing
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from flask import Flask

app = Flask(__name__)

@uwsgidecorators.postfork
def setup_tracing():
    start_tracing()
    # instrument our flask app instance eplicitly
    FlaskInstrumentor().instrument_app(app)

@app.route('/')
def hello_world():
    return 'Hello, World!'
```

##### Running with uWSGI:
```
uwsgi --http :9090 --wsgi-file app.py --callable app --master --enable-threads
```


## Manually instrument an application

Documentation on how to manually instrument a Python application is available
[here](https://opentelemetry-python.readthedocs.io/en/stable/getting-started.html).

## Troubleshooting

- Depending on the default python version on your system, you might want to use `pip3` and `python3` instead. 
- To be able to run `splk-py-trace` and `splk-py-trace-bootstrap`, the directory pip installs scripts to will
  have to be on your system's PATH environment variable. Generally, this works out of the box when using
  virtual environments, installing packages system-wide or in container images. In some cases, pip may install
  packages into your user local environment. In that case you'll need to add your Python user base's bin directory
  to your system path. You can find out your Python user base as follows by running `python -m site --user-base`.

  For example, if `python -m site --user-base` reports that `/Users/splunk/.local` as the Python user base, then
  you can add the directory to your path on Unix like system as follows:

  ```
  export PATH="/Users/splunk/.local/bin:$PATH"
  ```
- Enable debug logging like you would for any Python application.

  ```python
  import logging

  logging.basicConfig(level=logging.DEBUG)
  ```

  > :warning: Debug logging is extremely verbose and resource intensive. Enable
  > debug logging only when needed and disable when done.

# License and versioning

The Splunk distribution of OpenTelemetry Python Instrumentation is a
distribution of the [OpenTelemetry Python
project](https://github.com/open-telemetry/opentelemetry-python). It is
released under the terms of the Apache Software License version 2.0. See [the
license file](./LICENSE) for more details.
