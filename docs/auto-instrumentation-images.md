# Auto-instrumentation images

Release publishing creates two Python auto-instrumentation images:

- `quay.io/signalfx/splunk-otel-instrumentation-python:<tag>`
- `quay.io/signalfx/splunk-otel-instrumentation-python:<tag>-secureapp`

Both images are published for `linux/amd64` and `linux/arm64` under the same
tags. The container runtime automatically selects the AMD64 or ARM64 image
that matches the machine running the pod.

## Python compatibility

Both variants support **CPython 3.10–3.14** on glibc-based Linux. Each image
includes dependencies for all supported Python minor versions.

Each supported Python version has its own dependency directory. Identical files
share storage through relative symlinks, reducing the image and copied payload
size. Files that differ between versions stay separate.

The application and init image must use the same CPU architecture. Alpine/musl,
PyPy, free-threaded CPython, and Python versions outside this range are not
supported by these images.

Use the `<tag>-secureapp` image when the init container should also include the
Cisco SecureApp Python agent. SecureApp dependency logs require collector
routing to the SecureApp event endpoint; see
[SecureApp documentation](secureapp.md) and
[collector configuration example](examples/secureapp-collector-config.yaml).

## Build and test

Run these commands from the repository root to build and test both variants
locally without publishing:

```bash
docker buildx build --platform linux/amd64 --load -t python-init:test docker
docker buildx build --platform linux/amd64 --load -t python-init:test-secureapp \
  --build-arg REQUIREMENTS_FILE=requirements-secureapp.txt \
  --build-arg VERIFY_SECUREAPP=true docker
python3 tests/smoke/test-image-compatibility.py --image python-init:test --platform linux/amd64
python3 tests/smoke/test-image-compatibility.py --image python-init:test-secureapp \
  --secureapp --platform linux/amd64
```

Repeat with `linux/arm64`. These builds use the released distribution pinned in
`docker/requirements.txt`.

The tests verify the image payload across all supported Python versions with
environment-variable and `OTEL_CONFIG_FILE` configuration. They check trace,
metric, and log export through local OTLP gRPC and HTTP receivers without
backend credentials. Add `--python-version 3.13` to test one Python version.
SecureApp backend ingestion requires separate validation.
