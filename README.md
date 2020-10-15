# Splunk distribution of OpenTelemetry Python

The Splunk distribution of [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python)
provides multiple installable packages that automatically instruments your Python application to capture and report
distributed traces to SignalFx APM.

This Splunk distribution comes with the following defaults:

- [B3 context propagation](https://github.com/openzipkin/b3-propagation).
- [Zipkin exporter](https://zipkin.io/zipkin-api/#/default/post_spans)
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

| Environment variable          | Default value                        | Notes                                                                |
| ----------------------------- | ------------------------------------ | -------------------------------------------------------------------- |
| OTEL_PYTHON_ZIPKIN_ENDPOINT   | `http://localhost:9080/v1/trace`     | The Zipkin endpoint to connect to. Currently only HTTP is supported. |
| SPLK_SERVICE_NAME             | `unknown`                            | The service name of this JVM instance.                               |

### Trace configuration

| Environment variable          | Default value  | Purpose                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----------------------------- | -------------- | ------------------------------------------------------------------------------------                                                                                                                                                                                                                                                                                                                      |
| SPLK_MAX_ATTR_LENGTH          | unlimited      | Maximum length of string attribute value in characters. Longer values are truncated.                                                                                                                                                                                                                                                                                                                      |
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
opentelemetry-instrumentation-falcon>=0.14b0
opentelemetry-instrumentation-jinja2>=0.14b0
opentelemetry-instrumentation-requests>=0.14b0
opentelemetry-instrumentation-sqlite3>=0.14b0
opentelemetry-exporter-zipkin>=0.14b0
```

You can pipe the output of this command to append the new packages to your
requirements.txt file or to something like `poetry add`.

## Alternative: Instrument and configure by adding code

If you cannot use `splk-py-trace` command, you can also add a couple of lines
of code to your Python application to achieve the same result.

```python
from splunk_otel.tracing import start_tracing

start_tracing()

# rest of your python application's entrypoint script
```

### Manually configuring Celery workers

Celery workers must call the `start_tracing()` function after worker process is
initialized. If you are trying to trace a celery worker, you must use Celery's
`celery.signals.worker_process_init` signal to start tracing. For example:

```python
from splunk_otel.tracing import start_tracing
from celery.signals import worker_process_init

@worker_process_init.connect(weak=False)
def on_worker_process_init(*args, **kwargs):
    start_tracing()

# rest of your python application's entrypoint script
```

This is completely automated when using the `splk-py-trace` command to start
Python applications and is only required when instrumenting by hand.

Special Cases:

- Django
  - Needs env var `DJANGO_SETTINGS_MODULE` to be defined (can be found in `manage.py`)
- Celery
  - Supported automatically
  - When manual, use post worker init signal
- Gunicorn
  - Call `start_tracing()` in `post_fork()` hook in gunicorn settings.

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
