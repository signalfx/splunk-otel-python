#!/usr/bin/env bash
set -euo pipefail

# Smoke test for the splunk-opentelemetry Python package.
# Installs the package (local checkout or PyPI) and sends spans to Splunk O11y to
# verify end-to-end instrumentation works. Run this before a release (local) or
# after a release (--pypi) to validate the published package.
#
# Usage:
#   SPLUNK_ACCESS_TOKEN=<token> ./tests/smoke/smoke-test-package.sh          # local checkout
#   SPLUNK_ACCESS_TOKEN=<token> ./tests/smoke/smoke-test-package.sh --pypi   # PyPI package

: "${SPLUNK_ACCESS_TOKEN:?must be set}"

USE_PYPI=false
for arg in "$@"; do
    [ "$arg" = "--pypi" ] && USE_PYPI=true
done

SMOKE_VENV=/tmp/smoke-venv

if [ "$USE_PYPI" = "true" ]; then
    echo "==> Installing from PyPI..."
else
    echo "==> Installing from local checkout..."
fi

python -m venv "$SMOKE_VENV"
if [ "$USE_PYPI" = "true" ]; then
    "$SMOKE_VENV/bin/pip" install --quiet splunk-opentelemetry
else
    "$SMOKE_VENV/bin/pip" install --quiet .
fi

if [ "$USE_PYPI" = "true" ]; then
    echo "splunk-opentelemetry $("$SMOKE_VENV/bin/pip" show splunk-opentelemetry | grep ^Version | cut -d' ' -f2)"
fi

export SPLUNK_ACCESS_TOKEN
export SPLUNK_REALM="${SPLUNK_REALM:-us1}"
export OTEL_SERVICE_NAME="sop-smoke-package-$(date +%Y%m%d%H%M%S)"

"$SMOKE_VENV/bin/opentelemetry-instrument" \
  "$SMOKE_VENV/bin/python" tests/integration/trace_loop.py

echo "Done. Check APM on ${SPLUNK_REALM} for service '${OTEL_SERVICE_NAME}'."
