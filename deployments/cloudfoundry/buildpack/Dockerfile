FROM python:3.12-slim-bookworm AS install
COPY requirements.txt /requirements.txt
# Restrict wheels to the Linux AMD64 baseline supported by cflinuxfs4.
RUN python -m pip install --only-binary=:all: --no-compile \
    --platform manylinux2014_x86_64 --implementation cp --abi cp312 \
    --python-version 3.12 --target /payload/packages -r /requirements.txt
RUN PYTHONPATH=/payload/packages python -c \
    'from importlib.metadata import version; from pathlib import Path; Path("/payload/VERSION").write_text(version("splunk-opentelemetry") + "\n")'

FROM scratch
COPY --from=install /payload/ /
