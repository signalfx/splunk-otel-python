# Changelog

## Unreleased

## 0.10.0 (03-27-2021)

### Changed

- Upgraded OpenTelemetry to 1.0
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- `SPLUNK_MAX_ATTR_LENGTH` properly supported now. This env var was documented
  but due to a regression was not working anymore. This version adds proper
  support for it.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- `SPLUNK_TRACE_EXPORTER_URL` was replaced with `OTEL_EXPORTER_JAEGER_ENDPOINT`.
  [#26](https://github.com/signalfx/splunk-otel-python/pull/26)
- `start_tracing()` now accepts `access_token` and `max_attr_length` options.
  [#31](https://github.com/signalfx/splunk-otel-python/pull/31)
- `start_tracing()` now accepts an argument called `endpoint` instead of `url`.
  [#29](https://github.com/signalfx/splunk-otel-python/pull/29)

## 0.9.0 (03-13-2021)

### Changed

- Changed environment variable prefix from `SPLK_` to `SPLUNK_`. All environment
  variables must be updated for the library to continue to work.