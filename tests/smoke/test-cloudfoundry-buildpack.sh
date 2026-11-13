#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "$0")/../.." && pwd)"
archive="${1:?Usage: test-cloudfoundry-buildpack.sh BUILDPACK_ZIP}"
workspace="$(mktemp -d)"
container=""
cleanup() {
    if [[ -n "$container" ]]; then
        docker rm -f "$container" >/dev/null
    fi
    rm -rf "$workspace"
}
trap cleanup EXIT
unzip -q "$archive" -d "$workspace/buildpack"

for python_version in 3.10 3.11 3.12 3.13 3.14; do
    echo "Testing CPython $python_version on Linux AMD64..."
    container="$(docker create --platform linux/amd64 --user 65534:65534 \
        -e OTEL_SERVICE_NAME=cloudfoundry-smoke \
        -e OTEL_TRACES_EXPORTER=console \
        -e OTEL_METRICS_EXPORTER=none \
        -e OTEL_LOGS_EXPORTER=none \
        "python:$python_version-slim-bookworm" bash -euc '
            python -m pip install -q --target /tmp/appdeps -r /example/requirements.txt
            mkdir -p /tmp/staging/app /tmp/staging/cache /tmp/staging/deps
            CF_STACK=cflinuxfs4 /buildpack/bin/supply /tmp/staging/app /tmp/staging/cache /tmp/staging/deps 0 >&2
            mv /tmp/staging/deps /tmp/runtime-deps
            export PATH="/tmp/runtime-deps/0/bin:$PATH"
            export PYTHONPATH=/example:/tmp/appdeps
            cd /example
            splunk-otel-python python /test_payload.py
        ')"

    # Copy through Docker so the test also works with a remote CI daemon.
    docker cp "$workspace/buildpack" "$container:/buildpack"
    docker cp "$repository_dir/deployments/cloudfoundry/example" "$container:/example"
    docker cp "$repository_dir/tests/smoke/cloudfoundry_payload.py" "$container:/test_payload.py"
    docker start --attach "$container" > "$workspace/spans.json"
    exit_code="$(docker inspect --format '{{.State.ExitCode}}' "$container")"
    if [[ "$exit_code" != 0 ]]; then
        cat "$workspace/spans.json" >&2
        exit "$exit_code"
    fi

    python3 - "$workspace/spans.json" "$python_version" <<'PY'
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
print(f"CPython {sys.argv[2]}: native modules and SecureApp imported; Flask server span exported after relocation.")
PY
    docker rm "$container" >/dev/null
    container=""
done
