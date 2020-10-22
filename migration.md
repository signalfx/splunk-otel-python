# Migrating from signalfx-python-tracing

## Python3.5+ only

This library does not support Python 2 and in fact only supports Python3.5+. If you still need Python 2 support,
you should continue using signalfx-python-tracing.

## Remove signalfx-python-tracing

### Uninstall signalfx-python-tracing
First step is to uninstall `signalfx-python-tracing` and any libraries it might have pulled in as dependencies. You should remove the
package from your requirements.txt or pyproject.toml file. `signalfx-python-tracing` depends on a number of other packages that should
also be removed. Your package manager should be able to handle this automatically but here is a list of dependencies in case you need
to uninstall them manually:

```
opentracing
jaeger-python-client
```

### Uninstall instrumentation packages 
You should also remove any instrumentation packages automatically installed by the `sfx-py-trace-bootstrap` command. Below is a list of
all possible packages the boostrap command may have installed. You can safely remove them from your environment.


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

In addition to these, you should remove any other opentracing instrumentations you might be using.


## Install splunk-opentelemetry

Now that we've removed the OpenTracing based SignalFx Python library (signalfx-python-tracing), it is time to install the next-gen
OpenTelemetry based Python library called `splunk-opentelemetry`.

### Install splunk-opentelemtry

#### Using pip
```
pip install splunk-opentelemetry

```
You should also add `splunk-opentelemetry` to your requirements.txt file if you are using one.

#### Using poetry
```
poetry add splunk-opentelemetry
```

### Installing dependencies

Just like signalfx-python-tracing, splunk-openetelemetry also ships with a bootstrap command that automatically installs any
instrumentation packages your project could benefit from. The following command will detect and auto-install any instrumentations
for any packages it finds in your Python environment.

```
splk-py-trace-bootstrap
```

You can integrate this command in your build/deployment process so instrumentations are installed every time your project is deployed
or you can run this once during development and add all the installed packages as dependencies. The command also supports printing out
the list of instrumentation packages instead of automatically installing them. For example,

```
splk-py-trace-bootstrap -a=requirements

opentelemetry-instrumentation-falcon>=0.13b0
opentelemetry-instrumentation-requests>=0.8b0
opentelemetry-instrumentation-sqlite3>=0.11b0
opentelemetry-exporter-zipkin>=0.14b0
```

## Migrate configuration

### General Config

You must rename the following config environment variables

| Old Environment Variable           | New Environment Variable             |
| ---------------------------------- | ------------------------------------ |
| SIGNALFX_SERVICE_NAME              | SPLK_SERVICE_NAME                    |
| SIGNALFX_ENDPOINT_URL              | OTEL_EXPORTER_ZIPKIN_ENDPOINT        |
| SIGNALFX_RECORDED_VALUE_MAX_LENGTH | SPLK_MAX_ATTR_LENGTH                 |


### Django

#### Remove `signalfx_tracing` from INSTALLED_APPS

splunk-opentelemtry no longer ships a Django app and does not require you to add anything to your `INSTALLED_APPS` or any other
setting from settings.py

#### Set `DJANGO_SETTINGS_MODULE` environment variable

splunk-opentelemetry requires `DJANGO_SETTINGS_MODULE` environment to be set before it can auto-instrument a Django project. This
should be the same as the value set in your manage.py or wsgi.py app and should be a valid Python import path.

## Known issues

There are some known issues when migrating from signalfx-python-tracing to splunk-opentelemetry. These will be fixed in upcoming releases.

- OpenTelemetry's psycopg2 has a bug that prevents the driver from functioning correctly. Thus it has been disabled temporarily in this package.
- Does not yet support sending spans directly to the SignalFx backend and requires the SignalFx Smart Agent or OpenTelemetry collector.
- Does not yet support enabling or disabled specific instrumentations.
- Does not yet support tracing and log correlation. 