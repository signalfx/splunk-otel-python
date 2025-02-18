# Overview

This directory contains a Dockerfile and an `example-instrumentation.yaml` file for creating a
Docker init container that can be used to auto-instrumetation your Python app via the kubernetes
[OTel Operator](https://github.com/open-telemetry/opentelemetry-operator).

# Installation

Install [cert manager](https://cert-manager.io/docs/installation/) into your k8s cluster unless already installed.

Install the OTel Operator Custom Resource Definitions:

```
kubectl apply -f https://github.com/open-telemetry/opentelemetry-operator/releases/latest/download/opentelemetry-operator.yaml
```

Install an _OpenTelemetryCollector_ definition into the k8s cluster. The following defines a Collector sidecar that
just prints debug statements.

```yaml
apiVersion: opentelemetry.io/v1beta1
kind: OpenTelemetryCollector
metadata:
  name: my-sidecar
spec:
  mode: sidecar
  config:
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318
    exporters:
      debug: {}
    service:
      pipelines:
        traces:
          receivers: [otlp]
          exporters: [debug]
```

Install an _Instrumentation_ definition. It will be activated when you create an app with an `inject-python` annotation,
running an _init_ container before your Python app. The init container makes OTel libraries (including a
`sitecustomize.py`) available at `/otel-auto-instrumentation-python` and sets the PYTHONPATH for the starting
application.


```yaml
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: splunk-otel-python
spec:
  exporter:
    endpoint: http://localhost:4318
  sampler:
    type: always_on
  python:
    env:
      - name: OTEL_EXPORTER_OTLP_PROTOCOL
        value: http/protobuf
    image: "splunk-otel-python-init:v2.0.0"

```

Create an application image and run it via something like this Deployment. Note the annotations, indicating that
we want both Python auto instrumentation installed and our sidecar Collector to run.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ticker
spec:
  selector:
    matchLabels:
      app: ticker
  replicas: 1
  template:
    metadata:
      labels:
        app: ticker
      annotations:
        sidecar.opentelemetry.io/inject: "true"
        instrumentation.opentelemetry.io/inject-python: "true"
    spec:
      containers:
      - name: ticker
        image: ticker:v1
        env:
        - name: PYTHONUNBUFFERED
          value: "1"
```

When you run this application, k8s should create a pod with a Collector sidecar and auto instrumentation enabled. You
can check the Collector logs to make sure it's receiving data.
