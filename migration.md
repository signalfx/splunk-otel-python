# Migrate from the SignalFx Tracing Library for Python

The Splunk Distribution of OpenTelemetry Python replaces the SignalFx Tracing
Library for Python. If you’re using the SignalFx Tracing Library, migrate to
the Splunk Distribution of OpenTelemetry Python to use OpenTelemetry’s
instrumentation to send traces to Splunk APM. The Splunk Distribution of
OpenTelemetry Python uses OpenTelemetry to instrument applications, which is
an open-source API to gather telemetry data, and has a smaller footprint.

Because the SignalFx Tracing Library for Python uses OpenTracing and the Splunk Distribution
of OpenTelemetry Python uses OpenTelemetry, the semantic
conventions for span tag names change when you migrate. For more information,
see [Migrate from OpenTracing to OpenTelemetry](https://docs.signalfx.com/en/latest/apm/apm-getting-started/apm-opentelemetry-collector.html#apm-opentelemetry-migration).

## Known issues

These are the known issues as a result of migrating from the SignalFx Tracing Library for Python to the Splunk Distribution of OpenTelemetry Python:

- You can't inject trace context in logs right now.

## Requirements

This Splunk Distribution of OpenTelemetry requires Python 3.5 or later.
If you're still using Python 2, continue using the SignalFx Tracing Library
for Python.

## Steps

To migrate from the SignalFx Tracing Library for Python to the Splunk
Distribution of OpenTelemetry Python, remove the tracing library package,
uninstall any instrumentation packages the tracing library deployed, deploy
the Splunk Distribution of OpenTelemetry Python and its dependencies, and
migrate your existing configuration from the SignalFx tracing library.

Follow these streps to migrate to the Splunk Distribution of OpenTelemetry
Python.

### Step 1. Remove the SignalFx Tracing Library for Python

Follow these steps to remove the tracing library:

1. Uninstall `signalfx-tracing`:
   ```
   $ pip uninstall signalfx-tracing
   ```
2. Remove `signalfx-tracing` from your `requirements.txt` or `pyproject.toml`
   file.
3. If the package manager didn't remove every dependency for
   `signalfx-tracing`, remove them now:
   ```
   $ pip uninstall opentracing
   $ pip uninstall jaeger-client
   ```
4. Remove every instrumentation package the `sfx-py-trace-bootstrap` command
   installed. Here's a list of all the packages the tracing library could have
   installed:
   ```
    celery-opentracing
    django-opentracing
    elasticsearch-opentracing
    Flask-OpenTracing
    sfx-jaeger-client
    dbapi-opentracing
    pymongo-opentracing
    dbapi-opentracing
    redis-opentracing
    requests-opentracing
    signalfx-tracing
    tornado-opentracing
    ```
5. Remove any OpenTracing instrumentation packages you installed. 

### Step 2. Install the Splunk Distribution for OpenTelemetry Python

Follow these steps to deploy the Splunk Distribution for OpenTelemetry Python:

1. Install `splunk-opentelemetry[all]`:
   ```
   $ pip install splunk-opentelemetry
   ```
   You can also install the package with poetry:
   ```
   $ poetry add splunk-opentelemetry[all]
   ```
2. If you're using a `requirements.txt` or `pyproject.toml` file, add
   `splunk-opentelemetry[all]` to it.

3. Install instrumentations packages with the bootstrap
   command:
   ```
   splk-py-trace-bootstrap
   ```
   This command detects and installs instrumentation for every supported
   package it finds in your Python environment. To see which packages the
   command will install before running it, use this command:
   ```
   splk-py-trace-bootstrap -a=requirements
   ```
   You can integrate the bootstrap in your build/deployment process so
   instrumentation is configured every time you deploy the project. You can
   also run the bootstrap once during development and add all the
   instrumentation packages instead of automatically installing them.

### Step 3. Configure settings for the Splunk Distribution for OpenTelemetry

Migrate settings from the SignalFx tracing library to the Splunk Distribution
for OpenTelemetry:

Rename required environment variables:

| Old environment variable           | New environment variable             |
| ---------------------------------- | ------------------------------------ |
| SIGNALFX_ACCESS_TOKEN              | SPLUNK_ACCESS_TOKEN                  |
| SIGNALFX_SERVICE_NAME              | OTEL_SERVICE_NAME                    |
| SIGNALFX_ENDPOINT_URL              | OTEL_EXPORTER_JAEGER_ENDPOINT or OTEL_EXPORTER_OTLP_ENDPOINT |
| SIGNALFX_RECORDED_VALUE_MAX_LENGTH | SPLUNK_MAX_ATTR_LENGTH               |

### Step 3. Start you Python service

Run your python service with the `splk-py-trace` command. If you run your service as `python main.py`, you
can automatically instrument it with Splunk distribution of OpenTelemetry by running it as `splk-py-trace python main.py`.

## Special cases

### Django

This Splunk Distribution of OpenTelemetry doesn't ship a Django app, and
doesn't require you to add anything to your `INSTALLED_APPS`.

Follow these steps to update your Django configuration:

1. Remove `signalfx_tracing` from `INSTALLED_APPS` in your project's
   `settings.py`.
2. Set the `DJANGO_SETTINGS_MODULE` environment variable to the same value for
   the setting that's in `manage.py` or `wsgi.py`.
