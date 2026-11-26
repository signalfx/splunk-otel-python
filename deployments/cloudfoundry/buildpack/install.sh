#!/bin/sh
set -eu

python_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
packages="/payload/python$python_version"

# Resolve under each interpreter, using wheels compatible with the stack baseline.
python -m pip install --only-binary=:all: --no-compile \
    --platform manylinux2014_x86_64 --target "$packages" -r requirements-secureapp.txt

PYTHONPATH="$packages" python - <<'PY'
from importlib.metadata import version
from pathlib import Path

import splunk_secureapp_opentelemetry_extension

print("secureapp-python-agent", version("secureapp-python-agent"))
Path("/payload/VERSION").write_text(version("splunk-opentelemetry") + "\n")
PY
