#!/usr/bin/env bash
set -euo pipefail

# Smoke test for the splunk-otel-instrumentation-python Docker image.
# Run this after a release to validate the published image at quay.io.
#
# Simulates what the Kubernetes OTel Operator does: runs the init container to
# populate /autoinstrumentation into a shared volume, then runs a Python container
# with that volume on PYTHONPATH and sends sqlite3 spans to Splunk O11y.
#
# Usage:
#   SPLUNK_ACCESS_TOKEN=<token> ./tests/smoke/smoke-test-docker-image.sh
#   SPLUNK_ACCESS_TOKEN=<token> SPLUNK_REALM=eu0 ./tests/smoke/smoke-test-docker-image.sh
#   SPLUNK_ACCESS_TOKEN=<token> ./tests/smoke/smoke-test-docker-image.sh --image <image:tag>
#   SPLUNK_ACCESS_TOKEN=<token> ./tests/smoke/smoke-test-docker-image.sh --secureapp
#
# The --secureapp mode verifies the SecureApp image variant can populate
# /autoinstrumentation, import secureapp-python-agent, and send normal traces
# directly to Splunk O11y. It does not validate SecureApp dependency library
# ingestion, which requires collector routing to the SecureApp event endpoint.

: "${SPLUNK_ACCESS_TOKEN:?must be set}"

DEFAULT_IMAGE="quay.io/signalfx/splunk-otel-instrumentation-python:latest"
SECUREAPP_IMAGE="quay.io/signalfx/splunk-otel-instrumentation-python:latest-secureapp"
IMAGE="${DEFAULT_IMAGE}"
VERIFY_SECUREAPP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --secureapp) VERIFY_SECUREAPP=true; IMAGE="${SECUREAPP_IMAGE}"; shift ;;
        --image=*) IMAGE="${1#--image=}"; shift ;;
        --image)   IMAGE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

REALM="${SPLUNK_REALM:-us1}"
SERVICE_NAME="sop-smoke-docker-image-$(date +%Y%m%d%H%M%S)"
VOLUME="smoke-autoinstrumentation-$$"

cleanup() {
    docker volume rm "$VOLUME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Image: ${IMAGE}"
echo "==> Pulling image..."
docker pull --platform linux/amd64 "$IMAGE"

echo ""
echo "==> Running init container to populate /autoinstrumentation..."
docker run --rm --platform linux/amd64 \
    -v "${VOLUME}:/dest" \
    --entrypoint cp \
    "$IMAGE" \
    -r /autoinstrumentation/. /dest/

echo ""
echo "==> Sending spans to Splunk O11y (realm=${REALM}, service=${SERVICE_NAME})..."
if [ "${VERIFY_SECUREAPP}" = "true" ]; then
    echo "==> SecureApp mode verifies image contents/import and normal trace export only."
    echo "==> It does not validate SecureApp library ingestion; that requires collector routing to /v3/event."
fi
docker run --rm --platform linux/amd64 \
    -v "${VOLUME}:/autoinstrumentation:ro" \
    -e PYTHONPATH=/autoinstrumentation \
    -e OTEL_SERVICE_NAME="${SERVICE_NAME}" \
    -e SPLUNK_ACCESS_TOKEN="${SPLUNK_ACCESS_TOKEN}" \
    -e SPLUNK_REALM="${REALM}" \
    -e OTEL_BSP_SCHEDULE_DELAY=200 \
    -e VERIFY_SECUREAPP="${VERIFY_SECUREAPP}" \
    python:3.11-slim \
    /autoinstrumentation/bin/opentelemetry-instrument \
    python -c "
import importlib.metadata
import os
import sqlite3

if os.environ.get('VERIFY_SECUREAPP') == 'true':
    import splunk_secureapp_opentelemetry_extension
    print('secureapp-python-agent', importlib.metadata.version('secureapp-python-agent'))

conn = sqlite3.connect(':memory:')
cur = conn.cursor()
for i in range(12):
    cur.execute('SELECT ' + str(i))
from opentelemetry import trace
trace.get_tracer_provider().force_flush()
"

echo ""
echo "Done. Check APM on ${REALM} for service '${SERVICE_NAME}'."
