> The official Splunk documentation for this page is [Configure the Python agent](https://docs.signalfx.com/en/observability/gdi/get-data-in/application/python/configuration/advanced-python-otel-configuration.html#trace-propagation-configuration-python).
# Configuring Propagators

This package uses W3C trace context and W3C baggage propagators by default. You can override
this by setting the `OTEL_PROPAGATORS` environment variable to a comma separated list of one
more propagators. The SDK will use Python's entry points mechanism to load the specified
propagator implementation(s) and use it.

For example, to only use W3C trace context without baggage, you can set the environment variable
`OTEL_PROPAGATORS` environment variable to `tracecontext`.

You can specify any propagator name as long as the propagator implementation can be found via
entry points by that name.

## Configuring B3 propagator

If you'd like to use `b3` instead of or in addition to the default propagators, you can set `OTEL_PROPAGATORS` to `b3`
for [B3 single header](https://github.com/openzipkin/b3-propagation#single-header) or `b3multi` for
[B3 multi header](https://github.com/openzipkin/b3-propagation#multiple-headers) implementation. For example, to configure
your service to use B3 multi header and W3C baggage, set the environment variable as

```
OTEL_PROPAGATORS=b3multi,baggage
```

You can specify any combination of supported propagators. Choices are `tracecontext`, `baggae`, `b3` and `b3multi`. Note that
`b3` and `b3multi` are only available when the `opentelemetry-propagator-b3` package is installed. This is installed automatically
by installing `splunk-opentelemetry[all]` or `splunk-opentelemetry[b3]`.
