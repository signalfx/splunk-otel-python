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