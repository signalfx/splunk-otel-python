# Changelog

## Unreleased

## 1.0.0rc5 - 2021-09-20

### General

- Changed default for `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` to `12000`.
  [#135](https://github.com/signalfx/splunk-otel-python/pull/135)

## 0.17.0 - 2021-08-29

### General

- Upgraded Otel dependencies to 1.5.0 and 0.24.0b0
  [#116](https://github.com/signalfx/splunk-otel-python/pull/116)

### Breaking Changes

- SPLUNK_SERVICE_NAME and SPLUNK_MAX_ATTR_LENGTH env vars were removed.
  Use `OTEL_SERVICE_NAME` and `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` instead.
  [#116](https://github.com/signalfx/splunk-otel-python/pull/116)

## 1.0.0rc4 - 2021-08-04

### General

- Upgraded Otel dependencies to 1.4.1 and 0.23.0b2
  [#113](https://github.com/signalfx/splunk-otel-python/pull/113)

## 0.16.0 - 2021-08-04

### General

- Upgraded Otel dependencies to 1.4.1 and 0.23.0b2
  [#113](https://github.com/signalfx/splunk-otel-python/pull/113)

## 1.0.0rc3 - 2021-06-08

### Enhancements

- Pin exact Otel deps until 1.0
  [#88](https://github.com/signalfx/splunk-otel-python/pull/88)

## 1.0.0-rc2 - 2021-06-03

### General

- Upgrade OpenTelemetry Python to 1.3.0 and 0.22b0
  [#85](https://github.com/signalfx/splunk-otel-python/pull/85)

## 1.0.0-rc1 - 2021-06-01

### Breaking Changes

- Added `splunk-py-trace` and `splunk-py-trace-bootstrap` commands as replacements for `splunk-py-trace` and `splunk-py-trace-bootstrap` respectively.
  [#79](https://github.com/signalfx/splunk-otel-python/pull/79)
- Renamed `options.Options` to `options._Options` to make it private.
  [#74](https://github.com/signalfx/splunk-otel-python/pull/74)
- Deprecated `splunk-py-trace` and `splunk-py-trace-bootstrap` commands.
  [#79](https://github.com/signalfx/splunk-otel-python/pull/79)

### Enhancements

- Log trace correlation is enabled by default. Can be disabled by setting
  `OTEL_PYTHON_LOG_CORRELATION` env var to `false`.
  [#77](https://github.com/signalfx/splunk-otel-python/pull/77)

## 0.14.0 - 05-20-2021

### Breaking Changes

- Renamed `exporters` argument `span_exporter_factories` for `start_tracing()` function.
  [#71](https://github.com/signalfx/splunk-otel-python/pull/71)

## 0.13.0 - 05-17-2021

### Breaking Changes

- Removed support for `SPLK_` prefixed env var. 
  [#65](https://github.com/signalfx/splunk-otel-python/pull/65)
- Removed `opentelemetry-propagator-b3` as a depedency. It can be installed direclty or by using
  the new `b3` extras options e.g, `pip install splunk-opentelemetry[b3]`.
  [#58](https://github.com/signalfx/splunk-otel-python/pull/58)
- Removed Jaeger Thrift Exporter as a dependency. Users must chose the exporter they want to install
  when installing splunk-opentelemetry.
  [#60](https://github.com/signalfx/splunk-otel-python/pull/60)
- Changed default trace propagators to W3C trace context and W3C baggage.
  [#58](https://github.com/signalfx/splunk-otel-python/pull/58)
- `telemetry.auto.version` will now correctly refer to `opentelemetry-instrumentation` version being used.
  [#67](https://github.com/signalfx/splunk-otel-python/pull/67)
- Deprecated support for `SPLUNK_SERVICE_NAME` environment variable.
  Please use `OTEL_SERVICE_NAME=<my-service-name>` instead.
  [#57](https://github.com/signalfx/splunk-otel-python/pull/57)

### Enhancements

- Added `resource_attributes` config option to the `splunk_otel.start_tracing()` function.
  [#57](https://github.com/signalfx/splunk-otel-python/pull/57)
- Added support for `OTEL_SERVICE_NAME`.
  [#64](https://github.com/signalfx/splunk-otel-python/pull/64)
- Added support for OTLP gRPC span exporter and `OTEL_TRACES_EXPORTER` environment variable.
  [#60](https://github.com/signalfx/splunk-otel-python/pull/60)

## 0.12.0 - 04-21-2021

### Enhancements

- Added support trace response headers.
  [#44](https://github.com/signalfx/splunk-otel-python/pull/44)

## 0.11.0 - 03-29-2021

### Breaking Changes

- `start_tracing()` was moved from `splunk_otel.tracing` to `splunk_otel`.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- Removed support for `--exporters` CLI flag from `splunk-py-trace-bootstrap` command.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)

### Enchancements

- Added support for `--access-token` and `--service-name` to `splunk-py-trace` command.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- Updated splunk-py-trace and splunk-py-trace-bootstrap commands.
  Both commands now delegate to opentelemetry-instrument and opentelemetry-bootstrap commands.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- Allow all compatible versions for stable packages (API, SDK, exporters, propagators)
  and lock to exact version for unstable ones (instrumentations).
  ([#35](https://github.com/signalfx/splunk-otel-python/pull/35))

## 0.10.0 - 03-27-2021

### General

- Upgraded OpenTelemetry to 1.0 and 0.19b0
  ([#34](https://github.com/signalfx/splunk-otel-python/pull/34))

### Breaking Changes

- `SPLUNK_MAX_ATTR_LENGTH` properly supported now. This env var was documented
  but due to a regression was not working anymore. This version adds proper
  support for it.
  ([#34](https://github.com/signalfx/splunk-otel-python/pull/34))
- `SPLUNK_TRACE_EXPORTER_URL` was replaced with `OTEL_EXPORTER_JAEGER_ENDPOINT`.
  ([#26](https://github.com/signalfx/splunk-otel-python/pull/26))

### Enchancements
- `start_tracing()` now accepts `access_token` and `max_attr_length` options.
  ([#31](https://github.com/signalfx/splunk-otel-python/pull/31))
- `start_tracing()` now accepts an argument called `endpoint` instead of `url`.
  ([#29](https://github.com/signalfx/splunk-otel-python/pull/29))

## 0.9.0 - 03-13-2021

### Breaking Changes

- Changed environment variable prefix from `SPLK_` to `SPLUNK_`. All environment
  variables must be updated for the library to continue to work.
