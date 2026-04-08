# Profiling

This distro supports two profiling modes: **continuous profiling** and **call graph
profiling** (also called snapshot profiling). Both modes collect CPU stack traces and
export them as `pprof` data via the OTel logs exporter, with trace and span IDs
embedded so profiles can be correlated with traces in Splunk APM.

## Continuous profiling

Continuous profiling samples all threads at a fixed interval, regardless of whether
a trace is active. It gives a constant, low-overhead view of where your application
is spending CPU time.

### Enable

```sh
SPLUNK_PROFILER_ENABLED=true \
OTEL_SERVICE_NAME=my-service \
opentelemetry-instrument python app.py
```

### Configuration

| Environment variable                  | Default                                     | Description                                                                          |
|---------------------------------------|---------------------------------------------|--------------------------------------------------------------------------------------|
| `SPLUNK_PROFILER_ENABLED`             | `false`                                     | Set to `true` to enable continuous profiling.                                        |
| `SPLUNK_PROFILER_CALL_STACK_INTERVAL` | `1000`                                      | How often (in milliseconds) to collect a stack sample from all threads.              |
| `SPLUNK_PROFILER_LOGS_ENDPOINT`       | _(uses `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`)_ | Override the endpoint where profiling data is sent. Applies to both profiling modes. |

### How it works

A background thread fires at each `SPLUNK_PROFILER_CALL_STACK_INTERVAL` tick, collects
stack traces from every thread in the process (excluding the profiler thread itself),
and emits a `pprof` log record. If a thread is currently executing a span, that span's
`trace_id` and `span_id` are embedded as labels in the `pprof` sample, enabling
trace-to-profile correlation in the UI.

---

## Call graph profiling

Call graph profiling (also called snapshot profiling) only collects stacks for traces that
have been selected for profiling. It samples at 10ms intervals (vs. 1000ms for continuous profiling),
capturing a high-resolution picture of what the selected request was doing. This lets you
navigate from a specific slow trace in Splunk APM to its call graph, rather
than inferring behavior from low-frequency aggregated samples over a long time interval.

### Enable

```sh
SPLUNK_SNAPSHOT_PROFILER_ENABLED=true \
OTEL_SERVICE_NAME=my-service \
opentelemetry-instrument python app.py
```

### Configuration

| Environment variable                    | Default                                     | Description                                                                                   |
|-----------------------------------------|---------------------------------------------|-----------------------------------------------------------------------------------------------|
| `SPLUNK_SNAPSHOT_PROFILER_ENABLED`      | `false`                                     | Set to `true` to enable call graph profiling.                                                 |
| `SPLUNK_SNAPSHOT_SELECTION_PROBABILITY` | `0.01`                                      | Fraction of traces to profile, as a float between `0.0` and `1.0`. `0.01` means 1% of traces. |
| `SPLUNK_SNAPSHOT_SAMPLING_INTERVAL`     | `10`                                        | How often (in milliseconds) to collect a stack sample during an active profiled trace.        |
| `SPLUNK_PROFILER_LOGS_ENDPOINT`         | _(uses `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`)_ | Override the endpoint where profiling data is sent. Applies to both profiling modes.          |

### How it works

A trace is selected for profiling in one of two ways: the distro randomly selects it
based on `SPLUNK_SNAPSHOT_SELECTION_PROBABILITY`, or an upstream service has already
selected it and propagated that decision via baggage. In the latter case this service
profiles the request regardless of the local probability setting. Either way, the
decision propagates to downstream services so the entire trace is profiled consistently.
For each selected trace, the profiler collects stack traces from the active thread at the
interval set by `SPLUNK_SNAPSHOT_SAMPLING_INTERVAL`, filtering out threads not executing spans
from that trace. The profiler continues running for up to 60 seconds after the last selected
span ends, then pauses until the next selected trace arrives.

---

## Export format

Both modes export profiles as `pprof` data (gzip-compressed, base64-encoded) via the
OTel logs exporter. Each log record carries these attributes:

| Attribute                          | Value                                      |
|------------------------------------|--------------------------------------------|
| `profiling.data.format`            | `pprof-gzip-base64`                        |
| `profiling.data.type`              | `cpu`                                      |
| `profiling.instrumentation.source` | `continuous` or `snapshot`                 |
| `com.splunk.sourcetype`            | `otel.profiling`                           |
| `profiling.data.total.frame.count` | total number of stack frames in the record |

Each `pprof` sample includes labels for `trace_id`, `span_id`, `thread.id`,
`source.event.time`, and `source.event.period`.

---

## Troubleshooting

### A selected trace has no call graph data

In asynchronous or event-driven environments, a selected trace may have no call stack
data even when the request completed successfully. This is expected and typically occurs
when the application is waiting for an external operation, such as an HTTP or gRPC call
to a remote service, or when the request logic executes entirely between two sampling
intervals. In both cases no user code is actively running when the profiler fires, so
no stack is captured.

This reflects the limitations of sampling-based profiling and does not indicate a
misconfiguration.
