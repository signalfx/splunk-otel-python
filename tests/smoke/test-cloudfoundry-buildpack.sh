#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "$0")/../.." && pwd)"
archive="${1:?Usage: test-cloudfoundry-buildpack.sh BUILDPACK_ZIP}"
workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT
unzip -q "$archive" -d "$workspace/buildpack"

docker run --rm --platform linux/amd64 \
    -v "$workspace/buildpack:/buildpack:ro" \
    -v "$repository_dir/deployments/cloudfoundry/example:/example:ro" \
    -e OTEL_SERVICE_NAME=cloudfoundry-smoke \
    -e OTEL_TRACES_EXPORTER=console \
    -e OTEL_METRICS_EXPORTER=none \
    -e OTEL_LOGS_EXPORTER=none \
    python:3.12-slim-bookworm bash -euc '
        python -m pip install -q -r /example/requirements.txt
        mkdir -p /staging/app /staging/cache /staging/deps
        CF_STACK=cflinuxfs4 /buildpack/bin/supply /staging/app /staging/cache /staging/deps 0 >&2
        mv /staging/deps /runtime-deps
        export PATH="/runtime-deps/0/bin:$PATH"
        export PYTHONPATH=/example
        cd /example
        splunk-otel-python python -c '\''from app import app; response = app.test_client().get("/"); assert response.status_code == 200; assert response.json == {"message": "Hello from Cloud Foundry"}'\''
    ' > "$workspace/spans.json"

python3 - "$workspace/spans.json" <<'PY'
import json
from pathlib import Path
import sys

output = Path(sys.argv[1]).read_text().strip()
decoder = json.JSONDecoder()
spans = []
while output:
    span, end = decoder.raw_decode(output)
    spans.append(span)
    output = output[end:].lstrip()
assert any(
    span["kind"] == "SpanKind.SERVER"
    and span["resource"]["attributes"]["service.name"] == "cloudfoundry-smoke"
    for span in spans
), spans
print("Cloud Foundry buildpack smoke test passed: Flask server span exported after relocation.")
PY
