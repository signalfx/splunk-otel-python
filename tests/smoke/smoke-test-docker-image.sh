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

: "${SPLUNK_ACCESS_TOKEN:?must be set}"

DEFAULT_IMAGE="quay.io/signalfx/splunk-otel-instrumentation-python:latest"
IMAGE="${DEFAULT_IMAGE}"

while [[ $# -gt 0 ]]; do
    case "$1" in
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
docker run --rm --platform linux/amd64 \
    -v "${VOLUME}:/autoinstrumentation:ro" \
    -e PYTHONPATH=/autoinstrumentation \
    -e OTEL_SERVICE_NAME="${SERVICE_NAME}" \
    -e SPLUNK_ACCESS_TOKEN="${SPLUNK_ACCESS_TOKEN}" \
    -e SPLUNK_REALM="${REALM}" \
    -e OTEL_BSP_SCHEDULE_DELAY=200 \
    python:3.11-slim \
    /autoinstrumentation/bin/opentelemetry-instrument \
    python -c "
import sqlite3
conn = sqlite3.connect(':memory:')
cur = conn.cursor()
for i in range(12):
    cur.execute('SELECT ' + str(i))
from opentelemetry import trace
trace.get_tracer_provider().force_flush()
"

echo ""
echo "Done. Check APM on ${REALM} for service '${SERVICE_NAME}'."
