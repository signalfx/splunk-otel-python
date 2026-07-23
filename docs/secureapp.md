# SecureApp

The `secureapp` extra installs the Cisco SecureApp Python agent alongside the
Splunk OpenTelemetry Python distribution:

```bash
pip install "splunk-opentelemetry[secureapp]"
```

For Kubernetes operator auto-instrumentation, use the SecureApp Docker image
variant:

```text
quay.io/signalfx/splunk-otel-instrumentation-python:<tag>-secureapp
```

The SecureApp image is intended for Python application containers running Python
3.10 or later. The auto-instrumentation image contains native Python
dependencies, so the application container platform must match the image
platform.

## What SecureApp Sends

SecureApp reports runtime Python package dependencies through OpenTelemetry
logs. The dependency report records have:

- instrumentation scope: `secureapp`
- `event.name`: `com.cisco.secureapp.report.v1`

The report is about loaded runtime libraries. You do not need to install a known
vulnerable library to send a dependency report. If none of the reported
libraries match backend vulnerability data, the backend can show libraries with
zero vulnerabilities.

By default, SecureApp waits 60 seconds before the first dependency scan. For
smoke tests or short-lived apps, reduce the delay and log batch schedule:

```bash
export SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY=1
export OTEL_BLRP_SCHEDULE_DELAY=500
```

## Collector Routing

Direct ingest is fine for normal Splunk OpenTelemetry traces and metrics. For
SecureApp dependency library ingestion, use a Splunk OpenTelemetry Collector so
it can split SecureApp dependency logs from normal logs. The collector must
route only SecureApp dependency logs to the SecureApp event endpoint:

```yaml
connectors:
  routing/logs:
    default_pipelines: [logs/default]
    table:
      - context: log
        condition: instrumentation_scope.name == "secureapp"
        pipelines: [logs/secureapp]
```

The SecureApp pipeline exports to `/v3/event` and adds the SecureApp-specific
header:

```yaml
exporters:
  otlphttp/secureapp:
    logs_endpoint: https://ingest.${SPLUNK_REALM}.signalfx.com/v3/event
    headers:
      X-SF-TOKEN: ${SPLUNK_ACCESS_TOKEN}
      X-Splunk-Instrumentation-Library: secureapp
```

Do not send general application logs to `/v3/event`. Keep normal logs on their
regular logs pipeline and route only `instrumentation_scope.name == "secureapp"`
to the SecureApp pipeline. See
[examples/secureapp-collector-config.yaml](examples/secureapp-collector-config.yaml)
for a complete collector example.

## Why The Header Matters

`X-Splunk-Instrumentation-Library: secureapp` tells the ingest endpoint that the
OTLP log payload contains SecureApp event data. Without that header, the backend
can recognize the service but not process SecureApp dependency libraries.

The header should be attached only on the outbound exporter for the SecureApp
pipeline. Adding it to all logs is not equivalent, because normal application
logs should not be sent to the SecureApp event endpoint.

## Direct Ingest

`SPLUNK_REALM` configures the Splunk distro for direct trace and metric ingest,
but it does not by itself configure SecureApp dependency logs for `/v3/event`.

Direct SecureApp log ingest can only work if the application log exporter sends
to `/v3/event` and includes both required headers. That is not the recommended
general setup, because a single application log exporter cannot split SecureApp
logs from normal application logs. Use collector routing when the application
emits any non-SecureApp logs.

## Docker Smoke Test

`tests/smoke/smoke-test-docker-image.sh --secureapp` verifies that the published
SecureApp image variant can populate `/autoinstrumentation`, import
`secureapp-python-agent`, and send normal traces directly to Splunk Observability
Cloud.

That smoke test does not validate SecureApp library ingestion. Library ingestion
requires the collector route to `/v3/event` with
`X-Splunk-Instrumentation-Library: secureapp`.

## Troubleshooting

If the service appears in Splunk Observability Cloud but shows no libraries:

- Confirm the collector has a route for `instrumentation_scope.name == "secureapp"`.
- Confirm the SecureApp exporter uses `/v3/event`.
- Confirm the SecureApp exporter sets `X-Splunk-Instrumentation-Library: secureapp`.
- Confirm the SecureApp export path authenticates with an access token, either
  by setting `X-SF-TOKEN` on the exporter or by using a collector auth mechanism
  that adds it.
- Let the app run long enough for the dependency scan, or set
  `SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY=1` for testing.
- Confirm the app container platform matches the auto-instrumentation image
  platform when using the Docker image.
