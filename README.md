# Splunk Otel Python

The Splunk distribution of OpenTelemetry Python Instrumentation provides a Python agent that automatically instruments your Python application to capture and report distributed traces to SignalFx APM.

This Splunk distribution comes with the following defaults:

  * B3 context propagation.
  * Zipkin exporter configured to send spans to a locally running SignalFx Smart Agent (http://localhost:9080/v1/trace).
  * Unlimited default limits for configuration options to support full-fidelity traces.

## Getting Started

```
pip install splunk-opentelemetry'
splk-py-trace-bootstrap -a=install
splk-py-trace python main.py
```


## Development

### Installing packages

### Testing in a local project

In order to install and test the package in a local test project, we'll need to generate a setup.py file and then install an editable version of the package in the test project's environment. Assuming the test project environment lives at `/path/to/test/project/venv`, the following steps will install an editable version of package in the test project.

```
make develop
cd dev
. /path/to/test/project/venv/bin/activate
python setup.py develop
```

This will install an editable version of the package in the test project. Any changes made to the library will automatically reflect in the test project without the need to install the package again.