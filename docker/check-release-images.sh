#!/usr/bin/env bash
# Check that both Docker images build with the updated dependencies.
# The package on PyPI does not yet include these dependency upgrades.
# Build a package from the local code to test the upgraded dependencies.
#
# A successful run confirms that the required dependencies can be installed
# together. The script does not publish anything.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# Make a temporary copy of the Docker files so the checkout stays unchanged.
# Delete the temporary files when the script exits, even if a build fails.
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

cp -R "$repo_root/docker" "$work_dir/docker"
# Build a Python package (wheel) from the local code.
python3 -m pip wheel --no-deps --wheel-dir "$work_dir/wheels" "$repo_root"

# Change the temporary Docker files to install the local package.
python3 - "$work_dir" <<'PY'
import shutil
import sys
from pathlib import Path

work_dir = Path(sys.argv[1])
wheel = next((work_dir / "wheels").glob("splunk_opentelemetry-*.whl"))
context = work_dir / "docker"
shutil.copy2(wheel, context / wheel.name)
requirements = context / "requirements.txt"
lines = requirements.read_text().splitlines()
lines[0] = f"./{wheel.name}"
requirements.write_text("\n".join(lines) + "\n")
PY

# Build the standard and SecureApp images for AMD64 and ARM64.
# Each image includes packages for Python 3.10 through 3.14.
# Download dependencies again to check that pip can install all required versions.
# CI runs the image compatibility tests separately.
docker buildx build --pull --no-cache --platform linux/amd64,linux/arm64 \
    --output type=cacheonly --build-arg REQUIREMENTS_FILE=requirements.txt \
    "$work_dir/docker"
docker buildx build --pull --no-cache --platform linux/amd64,linux/arm64 \
    --output type=cacheonly --build-arg REQUIREMENTS_FILE=requirements-secureapp.txt \
    --build-arg VERIFY_SECUREAPP=true "$work_dir/docker"
