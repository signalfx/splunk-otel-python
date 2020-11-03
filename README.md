# Splunk distribution of OpenTelemetry Python

The Splunk distribution of [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python)
provides multiple installable packages that automatically instruments your Python application to capture and report
distributed traces to SignalFx APM.

This Splunk distribution comes with the following defaults:

- [B3 context propagation](https://github.com/openzipkin/b3-propagation).
- [Jaeger exporter](https://opentelemetry-python.readthedocs.io/en/stable/exporter/jaeger/jaeger.html)
  configured to send spans to a locally running [SignalFx Smart
  Agent](https://docs.signalfx.com/en/latest/apm/apm-getting-started/apm-smart-agent.html)
  (`http://localhost:9080/v1/trace`).
- Unlimited default limits for [configuration options](#trace-configuration) to support full-fidelity traces.

> :construction: This project is currently in **BETA**.

## Getting Started

The instrumentation works with Python version 3.5+. Supported
libraries are listed
[here](https://github.com/open-telemetry/opentelemetry-python/tree/master/instrumentation).

To get started, install the `splunk-opentelemetry` package, run the bootstrap script and wrap your run command with `splk-py-trace`.

For example, if the runtime parameters were:

```
python main.py --port=8000
```

Then the runtime parameters should be updated to:

```
$ pip install splunk-opentelemetry
$ splk-py-trace-bootstrap
$ SPLK_SERVICE_NAME=my-python-app \
    splk-py-trace python main.py --port=8000
```

The service name is the only configuration option that typically needs to be
specified. A couple other configuration options that may need to be changed or
set are:

* Endpoint if not sending to a locally running Smart Agent with default
  configuration
* Environment attribute (example:
  `OTEL_RESOURCE_ATTRIBUTES=environment=production`) to specify what
  environment the span originated from.

Instrumentation works by patching supported libraries at runtime with an
OpenTelemetry-compatible tracer to capture and export trace spans. The agent
also registers an OpenTelemetry `get_tracer` so you can support existing custom
instrumentation or add custom instrumentation to your application later.

To see the Python instrumentation in action with sample applications, see our
[examples](https://github.com/signalfx/tracing-examples/tree/master/signalfx-tracing/splunk-otel-python).

## All configuration options

### Zipkin exporter

| Environment variable          | Default value                        | Notes                                                                  |
| ----------------------------- | ------------------------------------ | ---------------------------------------------------------------------- |
| SPLK_TRACE_EXPORTER_URL       | `http://localhost:9080/v1/trace`     | The jaeger endpoint to connect to. Currently only HTTP is supported.   |
| SPLK_SERVICE_NAME             | `unnamed-python-service`             | The service name of this JVM instance.                                 |
| SPLK_ACCESS_TOKEN             |                                      | The optional organization access token for trace submission requests.  |

### Trace configuration

| Environment variable          | Default value  | Purpose                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----------------------------- | -------------- | ------------------------------------------------------------------------------------                                                                                                                                                                                                                                                                                                                      |
| SPLK_MAX_ATTR_LENGTH          | 1200            | Maximum length of string attribute value in characters. Longer values are truncated.                                                                                                                                                                                                                                                                                                                      |
| OTEL_RESOURCE_ATTRIBUTES      | unset          | Comma-separated list of resource attributes added to every reported span. <details><summary>Example</summary>`key1=val1,key2=val2`</details>
| OTEL_TRACE_ENABLED            | `true`         | Globally enables tracer creation and auto-instrumentation.                                                                                                                                                                                                                                                                                                                                                |

## Advanced Getting Started

### Alternative: List requirements instead of installing them

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
opentelemetry-exporter-jaeger>=0.15b0
```

You can pipe the output of this command to append the new packages to your
requirements.txt file or to something like `poetry add`.

### Alternative: Instrument and configure by adding code

If you cannot use `splk-py-trace` command, you can also add a couple of lines
of code to your Python application to achieve the same result.

```python
from splunk_otel.tracing import start_tracing

start_tracing()

# rest of your python application's entrypoint script
```

## Exporting to Smart Agent, Otel collector or SignalFx ingest

This package exports spans in Jaeger Thrift format over HTTP and supports exporting to the SignalFx Smart Agent,
OpenTelemetry collector and directly to SignalFx ingest API. You can use `SPLK_TRACE_EXPORTER_URL` environment variable
to specify an export URL. The value must be a full URL including scheme and path.

### Smart Agent

This is the default option. You do not need to set any config options if you want to export to the Smart Agent and
you are running the agent on the default port (`9080`). The exporter will default to `http://localhost:9080/v1/trace`
when the environment variable is not specified.

### OpenTelemetry Collector

In order to do this, you'll need to enable Jaeger Thrift HTTP receiver on OpenTelemetry Collector and set 
`SPLK_TRACE_EXPORTER_URL` to `http://localhost:14268/api/traces` assuming the collector is reachable via localhost.

### SignalFx Ingest API

In order to send traces directly to SignalFx ingest API, you need to:

1. Set `SPLK_TRACE_EXPORTER_URL` to `https://ingest.<realm>.signalfx.com/v2/trace` where `realm` is your
SignalFx realm e.g, `https://ingest.us0.signalfx.com/v2/trace`.
2. Set `SPLK_ACCESS_TOKEN` to one of your SignalFx APM access tokens. 


### Special Cases:

#### Celery
Tracing Celery workers works out of the box when you use the `splk-py-trace` command to start your Python application.
However, if you are instrumenting your celery workers with code, you'll need to make sure you setup tracing for each
worker by using Celery's `celery.signalfx.worker_process_init` signal. For example:

```python
from splunk_otel.tracing import start_tracing
from celery.signals import worker_process_init

@worker_process_init.connect(weak=False)
def on_worker_process_init(*args, **kwargs):
    start_tracing()

# rest of your python application's entrypoint script
```

#### Django
Automatically instrumenting Django requires `DJANGO_SETTINGS_MODULE` environment variable to be set.
The value should be the same as set in your `manage.py` or `wsgi.py` modules. For example, if your manage.py
file sets this environment variable to `mydjangoproject.settings` and you start your Django project as
`./manage.py runserver`, then you can automatically instrument your Django project as follows:

```
export DJANGO_SETTINGS_MODULE=mydjangoproject.settings
splk-py-trace ./manage.py runserver
```

#### Gunicorn
Like Celery, we'll also need to setup tracing per Gunicorn worker. This can be done by setting up tracing inside
Gunicorn's `post_fork()` handler. For exampleL

```python
# gunicorn.config.py
from splunk_otel.tracing import start_tracing

def post_fork(server, worker):
    start_tracing()
```

Then add `-c gunicorn.config.py` CLI flag to your gunicorn command.


## Manually instrument an application

Documentation on how to manually instrument a Python application is available
[here](https://opentelemetry-python.readthedocs.io/en/stable/getting-started.html).

## Troubleshooting

Enable debug logging like you would for any Python application.

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

> :warning: Debug logging is extremely verbose and resource intensive. Enable
> debug logging only when needed and disable when done.

# License and versioning

The Splunk distribution of OpenTelemetry Python Instrumentation is a distribution
of the [OpenTelemetry Python
project](https://github.com/open-telemetry/opentelemetry-python).
It is released under the terms of the Apache Software License version 2.0. See
[the license file](./LICENSE) for more details.
