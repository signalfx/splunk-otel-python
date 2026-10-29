# Keep complete installations separate: wheels and dependency markers can differ
# between interpreters, even when the distribution versions are the same.
FROM python:3.10-slim-bookworm AS py310
WORKDIR /operator-build
ARG REQUIREMENTS_FILE=requirements.txt
ARG VERIFY_SECUREAPP=false
COPY . .
RUN ./install.sh

FROM python:3.11-slim-bookworm AS py311
WORKDIR /operator-build
ARG REQUIREMENTS_FILE=requirements.txt
ARG VERIFY_SECUREAPP=false
COPY . .
RUN ./install.sh

FROM python:3.12-slim-bookworm AS py312
WORKDIR /operator-build
ARG REQUIREMENTS_FILE=requirements.txt
ARG VERIFY_SECUREAPP=false
COPY . .
RUN ./install.sh

FROM python:3.13-slim-bookworm AS py313
WORKDIR /operator-build
ARG REQUIREMENTS_FILE=requirements.txt
ARG VERIFY_SECUREAPP=false
COPY . .
RUN ./install.sh

FROM python:3.14-slim-bookworm AS py314
WORKDIR /operator-build
ARG REQUIREMENTS_FILE=requirements.txt
ARG VERIFY_SECUREAPP=false
COPY . .
RUN ./install.sh

FROM py310 AS assemble
COPY --from=py310 /operator-build/workspace /autoinstrumentation/python3.10
COPY --from=py311 /operator-build/workspace /autoinstrumentation/python3.11
COPY --from=py312 /operator-build/workspace /autoinstrumentation/python3.12
COPY --from=py313 /operator-build/workspace /autoinstrumentation/python3.13
COPY --from=py314 /operator-build/workspace /autoinstrumentation/python3.14
COPY deduplicate.py /operator-build/deduplicate.py
RUN python /operator-build/deduplicate.py /autoinstrumentation

FROM busybox
COPY --from=assemble /autoinstrumentation /autoinstrumentation
COPY sitecustomize.py /autoinstrumentation/opentelemetry/instrumentation/auto_instrumentation/sitecustomize.py
RUN chmod -R go+rX /autoinstrumentation
