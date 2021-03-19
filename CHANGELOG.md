# Changelog

## Unreleased

### Changed

- `init_tracing()` now accepts an argument called `endpoint` instead of `url`.
- `SPLUNK_TRACE_EXPORTER_URL` was replaced with `OTEL_EXPORTER_JAEGER_ENDPOINT`.

## 0.9.0 (03-13-2021)

### Changed

- Changed environment variable prefix from `SPLK_` to `SPLUNK_`. All environment
  variables must be updated for the library to continue to work.