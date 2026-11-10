FROM python:3.10-slim-bookworm AS py310
WORKDIR /build
COPY . .
RUN sh install.sh

FROM python:3.11-slim-bookworm AS py311
WORKDIR /build
COPY . .
RUN sh install.sh

FROM python:3.12-slim-bookworm AS py312
WORKDIR /build
COPY . .
RUN sh install.sh

FROM python:3.13-slim-bookworm AS py313
WORKDIR /build
COPY . .
RUN sh install.sh

FROM python:3.14-slim-bookworm AS py314
WORKDIR /build
COPY . .
RUN sh install.sh

FROM scratch
COPY --from=py310 /payload/VERSION /VERSION
COPY --from=py310 /payload/python3.10 /python3.10
COPY --from=py311 /payload/python3.11 /python3.11
COPY --from=py312 /payload/python3.12 /python3.12
COPY --from=py313 /payload/python3.13 /python3.13
COPY --from=py314 /payload/python3.14 /python3.14
