#!/usr/bin/env bash
set -euo pipefail

# Local SecureApp direct-ingest smoke test.
#
# Reads SPLUNK_ACCESS_TOKEN from the environment, or from macOS pbpaste when the
# environment variable is unset. The token is exported for the child process but
# is never printed.
#
# Optional overrides:
#   SPLUNK_REALM=us1
#   OTEL_SERVICE_NAME=secureapp-direct-ingest-...
#   SECUREAPP_SMOKE_VENV=/tmp/secureapp-direct-ingest-smoke
#   SECUREAPP_SMOKE_APP=tests/integration/secureapp_extra.py
#   SECUREAPP_EXTRA_RUNTIME_SECONDS=60
#   PYTHON_BIN=python3

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -z "${SPLUNK_ACCESS_TOKEN:-}" ]]; then
  if command -v pbpaste >/dev/null 2>&1; then
    SPLUNK_ACCESS_TOKEN="$(pbpaste | tr -d '\r\n')"
    export SPLUNK_ACCESS_TOKEN
  else
    echo "SPLUNK_ACCESS_TOKEN is unset and pbpaste is unavailable." >&2
    echo "Set SPLUNK_ACCESS_TOKEN and rerun this script." >&2
    exit 1
  fi
fi

if [[ -z "${SPLUNK_ACCESS_TOKEN}" ]]; then
  echo "SPLUNK_ACCESS_TOKEN is empty." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${SECUREAPP_SMOKE_VENV:-/tmp/secureapp-direct-ingest-smoke}"
APP_PATH="${SECUREAPP_SMOKE_APP:-tests/integration/secureapp_extra.py}"

export SPLUNK_REALM="${SPLUNK_REALM:-us1}"
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-secureapp-direct-ingest-$(date +%Y%m%d%H%M%S)}"

export OTEL_EXPORTER_OTLP_PROTOCOL="${OTEL_EXPORTER_OTLP_PROTOCOL:-http/protobuf}"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:-https://ingest.${SPLUNK_REALM}.observability.splunkcloud.com/v2/log/otlp}"

export SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY="${SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY:-1}"
export SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL="${SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL:-1}"
export OTEL_BLRP_SCHEDULE_DELAY="${OTEL_BLRP_SCHEDULE_DELAY:-500}"
export SECUREAPP_EXTRA_RUNTIME_SECONDS="${SECUREAPP_EXTRA_RUNTIME_SECONDS:-60}"

echo "Creating smoke venv: ${VENV_DIR}"
rm -rf "${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

echo "Installing local splunk-opentelemetry[secureapp]"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -e ".[secureapp]"

echo "Running SecureApp direct-ingest smoke"
echo "  realm:        ${SPLUNK_REALM}"
echo "  service.name: ${OTEL_SERVICE_NAME}"
echo "  logs:         ${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT}"
echo "  runtime:      ${SECUREAPP_EXTRA_RUNTIME_SECONDS}s"
echo

"${VENV_DIR}/bin/opentelemetry-instrument" \
  "${VENV_DIR}/bin/python" "${APP_PATH}"

echo
echo "Done. Check Splunk Observability Cloud for service '${OTEL_SERVICE_NAME}'."
