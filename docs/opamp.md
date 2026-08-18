# OpAMP

Splunk OTel Python provides OpAMP support. When enabled, the OpAMP client
connects to the configured endpoint and reports the Python agent's status and
settings. Agents connected to Splunk Observability Cloud appear on the Fleet
Management page.

OpAMP support is provisional. Remote configuration is not supported yet.
When `OTEL_CONFIG_FILE` is set, OpAMP does not report the declarative file as
effective configuration. OpAMP continues to report settings derived from
environment variables.

## Default connection

```text
Python process -> Splunk OpenTelemetry Collector -> Splunk Observability Cloud
```

The Python process sends OpAMP messages to
`http://localhost:4320/v1/opamp` by default. The collector must listen on that
address and forward the messages to Splunk Observability Cloud.

## Enable OpAMP

```sh
SPLUNK_OPAMP_ENABLED=true \
opentelemetry-instrument python app.py
```

## Settings

| Environment variable               | Default                            | Description                    |
|------------------------------------|------------------------------------|--------------------------------|
| `SPLUNK_OPAMP_ENABLED`             | `false`                            | Set to `true` to enable OpAMP. |
| `SPLUNK_OPAMP_ENDPOINT`            | `http://localhost:4320/v1/opamp`   | OpAMP endpoint.                |
| `SPLUNK_OPAMP_POLLING_INTERVAL`    | `30000`                            | Report interval, in milliseconds. |


## Troubleshooting

Open **Data Management > Fleet Management > Instrumentation** in Splunk
Observability Cloud. If OpAMP is enabled, the Python agent should show `Connected`.

If it does not:

- When using the default endpoint, check that the collector listens on port `4320`.
- Check the collector endpoint and access token.
- Check the application logs for `Connection to OpAMP server failed`.
