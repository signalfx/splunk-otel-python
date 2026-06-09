# Builds both the standard and SecureApp Python auto-instrumentation images.
# Pass REQUIREMENTS_FILE=requirements-secureapp.txt for the SecureApp variant.
FROM python:3.11 AS build

WORKDIR /operator-build

# The release script uses requirements-secureapp.txt for the SecureApp image
# variant and leaves the default requirements.txt for the standard image.
ARG REQUIREMENTS_FILE=requirements.txt
ARG VERIFY_SECUREAPP=false

COPY requirements*.txt ./

RUN mkdir workspace && pip install --target workspace -r "$REQUIREMENTS_FILE"

# Fail the SecureApp image build early if the selected requirements file did not
# install the SecureApp extension into /autoinstrumentation.
RUN if [ "$VERIFY_SECUREAPP" = "true" ]; then \
      PYTHONPATH=workspace python -c "import importlib.metadata; import splunk_secureapp_opentelemetry_extension; print('secureapp-python-agent', importlib.metadata.version('secureapp-python-agent'))"; \
    fi

FROM busybox

COPY --from=build /operator-build/workspace /autoinstrumentation

RUN chmod -R go+r /autoinstrumentation
