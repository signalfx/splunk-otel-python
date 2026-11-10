FROM python:3.12-slim-bookworm AS install
WORKDIR /build
COPY . .
# Restrict wheels to the Linux AMD64 baseline supported by cflinuxfs4.
RUN python -m pip install --only-binary=:all: --no-compile \
    --platform manylinux2014_x86_64 --implementation cp --abi cp312 \
    --python-version 3.12 --target /payload/packages -r requirements-secureapp.txt
RUN PYTHONPATH=/payload/packages python -c \
    'from importlib.metadata import version; from pathlib import Path; import splunk_secureapp_opentelemetry_extension; print("secureapp-python-agent", version("secureapp-python-agent")); Path("/payload/VERSION").write_text(version("splunk-opentelemetry") + "\n")'

FROM scratch
COPY --from=install /payload/ /
