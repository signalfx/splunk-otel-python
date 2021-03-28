# Changelog

## Unreleased

### Added

- Added support for `--access-token` and `--service-name` to `splk-py-trace` command.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)

### Changed

- Updated splk-py-trace and splk-py-trace-bootstrap commands.
  Both commands now delegate to opentelemetry-instrument and opentelemetry-bootstrap commands.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- `start_tracing()` was moved from `splunk_otel.tracing` to `splunk_otel`.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)
- Allow all compatible versions for stable packages (API, SDK, exporters, propagators)
  and lock to exact version for unstable ones (instrumentations).
  ([#35](https://github.com/signalfx/splunk-otel-python/pull/35))

### Removed

- Removed support for `--exporters` CLI flag from `splk-py-trace-bootstrap` command.
  [#34](https://github.com/signalfx/splunk-otel-python/pull/34)


## 0.10.0 (03-27-2021)

### Changed

- Upgraded OpenTelemetry to 1.0
  ([#34](https://github.com/signalfx/splunk-otel-python/pull/34))
- `SPLUNK_MAX_ATTR_LENGTH` properly supported now. This env var was documented
  but due to a regression was not working anymore. This version adds proper
  support for it.
  ([#34](https://github.com/signalfx/splunk-otel-python/pull/34))
- `SPLUNK_TRACE_EXPORTER_URL` was replaced with `OTEL_EXPORTER_JAEGER_ENDPOINT`.
  ([#26](https://github.com/signalfx/splunk-otel-python/pull/26))
- `start_tracing()` now accepts `access_token` and `max_attr_length` options.
  ([#31](https://github.com/signalfx/splunk-otel-python/pull/31))
- `start_tracing()` now accepts an argument called `endpoint` instead of `url`.
  ([#29](https://github.com/signalfx/splunk-otel-python/pull/29))

## 0.9.0 (03-13-2021)

### Changed

- Changed environment variable prefix from `SPLK_` to `SPLUNK_`. All environment
  variables must be updated for the library to continue to work.