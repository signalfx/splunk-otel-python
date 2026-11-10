#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 2 ]]; then
    echo "Usage: build.sh [OUTPUT_ZIP [AGENT_WHEEL]]" >&2
    exit 1
fi

buildpack_dir="$(cd "$(dirname "$0")" && pwd)"
repository_dir="$(cd "$buildpack_dir/../../.." && pwd)"
output="${1:-$buildpack_dir/splunk_otel_python_buildpack-linux.zip}"
workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT

# Keep the init image's instrumentation pins when CI supplies a checkout wheel.
mkdir -p "$workspace/context"
if [[ $# -eq 2 ]]; then
    cp "$2" "$workspace/context/"
    {
        printf './%s\n' "$(basename "$2")"
        tail -n +2 "$repository_dir/docker/requirements.txt"
    } > "$workspace/context/requirements.txt"
else
    cp "$repository_dir/docker/requirements.txt" "$workspace/context/requirements.txt"
fi

docker build --platform linux/amd64 \
    --file "$buildpack_dir/Dockerfile" \
    --output "type=local,dest=$workspace/buildpack/agent" \
    "$workspace/context"

cp -R "$buildpack_dir/bin" "$workspace/buildpack/bin"
cp "$buildpack_dir/launch.py" "$buildpack_dir/run" "$buildpack_dir/manifest.yml" "$workspace/buildpack/"
chmod +x "$workspace/buildpack/bin/"* "$workspace/buildpack/run"
(cd "$workspace/buildpack" && zip -qr "$workspace/buildpack.zip" .)
mv "$workspace/buildpack.zip" "$output"
echo "Created $output"
