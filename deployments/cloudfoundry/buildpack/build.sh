#!/usr/bin/env bash
set -euo pipefail

buildpack_dir="$(cd "$(dirname "$0")" && pwd)"
repository_dir="$(cd "$buildpack_dir/../../.." && pwd)"
output="${1:-$buildpack_dir/splunk_otel_python_buildpack-linux.zip}"
workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT

# Reuse the distribution and instrumentation versions from the Python init image.
docker build --platform linux/amd64 \
    --file "$buildpack_dir/Dockerfile" \
    --output "type=local,dest=$workspace/buildpack/agent" \
    "$repository_dir/docker"

cp -R "$buildpack_dir/bin" "$workspace/buildpack/bin"
cp "$buildpack_dir/launch.py" "$buildpack_dir/run" "$buildpack_dir/manifest.yml" "$workspace/buildpack/"
chmod +x "$workspace/buildpack/bin/"* "$workspace/buildpack/run"
(cd "$workspace/buildpack" && zip -qr "$workspace/buildpack.zip" .)
mv "$workspace/buildpack.zip" "$output"
echo "Created $output"
