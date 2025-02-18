FROM python:3.11 AS build

WORKDIR /operator-build

ADD requirements.txt .

RUN mkdir workspace && pip install --target workspace -r requirements.txt

FROM busybox

COPY --from=build /operator-build/workspace /autoinstrumentation

RUN chmod -R go+r /autoinstrumentation
