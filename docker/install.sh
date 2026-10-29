#!/bin/sh
set -eu

# Require wheels so a missing platform/interpreter build fails at build time.
python -m pip install --no-cache-dir --only-binary=:all: --no-compile \
    --target workspace -r "$REQUIREMENTS_FILE"

if [ "$VERIFY_SECUREAPP" = "true" ]; then
    PYTHONPATH=workspace python -B -c 'import importlib.metadata; import splunk_secureapp_opentelemetry_extension; print("secureapp-python-agent", importlib.metadata.version("secureapp-python-agent"))'
fi
