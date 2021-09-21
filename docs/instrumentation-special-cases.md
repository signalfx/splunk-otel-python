> The official Splunk documentation for this page is [Additional instructions for Python frameworks](https://docs.signalfx.com/en/observability/gdi/get-data-in/application/python/instrumentation/instrument-python-frameworks.html). For instructions on how to contribute to the docs, see [CONTRIBUTE.md](../CONTRIBUTE.md).

# Instrumentation Special Cases

## Celery

Tracing Celery workers works out of the box when you use the `splunk-py-trace`
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

## Django

Automatically instrumenting Django requires `DJANGO_SETTINGS_MODULE`
environment variable to be set. The value should be the same as set in your
`manage.py` or `wsgi.py` modules. For example, if your manage.py file sets this
environment variable to `mydjangoproject.settings` and you start your Django
project as `./manage.py runserver`, then you can automatically instrument your
Django project as follows:

```
export DJANGO_SETTINGS_MODULE=mydjangoproject.settings
splunk-py-trace ./manage.py runserver
```

## Gunicorn

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

## UWSGI

When using UWSGI, tracing must be setup as a response to the `post_fork` signal.

For example:

```python
import uwsgidecorators
from splunk_otel.tracing import start_tracing

@uwsgidecorators.postfork
def setup_tracing():
    start_tracing()

```

### Running with uwsgi

```
uwsgi --http :9090 --wsgi-file <your_app.py> --callable <your_wsgi_callable> --master --enable-threads
```

The above snippet should be placed in the main python script that uwsgi imports
and loads.

### UWSGI and Flask

Using USWGI with Flask requires one additional little step. Calling
`start_tracing()` does not auto-instrument pre-existing flask app instances but
only flask instances created after. When running flask with uwsgi, we need to
create a new flask app instance before the post_fork signal is emitted. This
means your flask app will not be auto-instrumented. However, you can still
auto-instrument an existing flask app explicitly by importing and calling the
flask instrumentor.

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

#### Running with uWSGI:

```
uwsgi --http :9090 --wsgi-file app.py --callable app --master --enable-threads
```
