# Splunk Otel Python

The Splunk distribution of OpenTelemetry Python Instrumentation provides a Python agent that automatically instruments your Python application to capture and report distributed traces to SignalFx APM.

This Splunk distribution comes with the following defaults:

  * B3 context propagation.
  * Zipkin exporter configured to send spans to a locally running SignalFx Smart Agent (http://localhost:9080/v1/trace).
  * Unlimited default limits for configuration options to support full-fidelity traces.

## Getting Started

### 1. Install the package

This will install splunk-opentelemetry and any other packages required to start tracing a Python application.

```
pip install splunk-opentelemetry
```

### 2. Detect and install instrumentations

This will detect installed packages in your active Python environment and install the relevant instrumentation
packages.

```
splk-py-trace-bootstrap
```

#### Alternative: List requirements instead of installing them

The `splk-py-trace-bootstrap` command can optionally print out the list of packages it would install if you chose.
In order to do so, pass `-a=requirements` CLI argument to it. For example,

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

You can pipe the output of this command to append the new packages to your requirements.txt file or to something like `poetry add`.

### 3. Automatically trace your python application

With all the packages required to trace and instrument your application installed, you can start your application using the `splk-py-trace`
command to auto-instrument and auto-configure tracing. For example, if you usually start your Python application as `python main.py --port=8000`,
you'd have to change it to the following command:

```
splk-py-trace python main.py --port=8000
```

#### Alternative: Instrument and configure by adding code

If you cannot use `splk-py-trace` command, you can also add a couple of lines of code to your Python application to acheive the same result.

```python
from splunk_otel.tracing import start_tracing

start_tracing()

# rest of your python application's entrypoint script
```

##### Manually configuring Celery workers

Celery workers must call the `start_tracing()` function after worker process is initialized. If you are trying to trace a celery worker,
you must use Celery's `celery.signals.worker_process_init` signal to start tracing. For example:

```python
from splunk_otel.tracing import start_tracing
from celery.signals import worker_process_init

@worker_process_init.connect(weak=False)
def on_worker_process_init(*args, **kwargs):
    start_tracing()

# rest of your python application's entrypoint script
```

This is completely automated when using the `splk-py-trace` command to start Python applications and is only required when instrumenting
by hand.

## Special Cases 

### Django
- Needs env var `DJANGO_SETTINGS_MODULE` to be defined (can be found in manage.py)

### Celery
- support automatically
- when manual, use post worker init signal

### Gunicorn
- call `start_tracing()` in `post_fork()` hook in gunicorn settings.


## Development

### Bootstraping 

#### Install Poetry

This project uses poetry to manage dependencies and the package. Follow the instructions here to install Poetry on your system: https://python-poetry.org/docs/#installation

#### Install dependencies

Once poetry is installed and available run the following command to install all package required for local development.

```
make dep
```

### Testing in a local project

In order to install and test the package in a local test project, we'll need to generate a setup.py file and then install an editable version of the package in the test project's environment. Assuming the test project environment lives at `/path/to/test/project/venv`, the following steps will install an editable version of package in the test project.

```
make develop
cd dev
. /path/to/test/project/venv/bin/activate
python setup.py develop
```

This will install an editable version of the package in the test project. Any changes made to the library will automatically reflect in the test project without the need to install the package again.
