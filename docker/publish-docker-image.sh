#!/usr/bin/env bash
set -e

cd docker

release_tag="$1" # e.g. v1.2.3
major_version=$(echo $release_tag | cut -d '.' -f1) # e.g. "v1"
repo="quay.io/signalfx/splunk-otel-instrumentation-python"

build_docker_image() {
  echo ">>> Building the operator docker image ..."
  docker build -t splunk-otel-instrumentation-python .
  docker tag splunk-otel-instrumentation-python ${repo}:latest
  docker tag splunk-otel-instrumentation-python ${repo}:${major_version}
  docker tag splunk-otel-instrumentation-python ${repo}:${release_tag}
}

login_to_quay_io() {
  echo ">>> Logging into quay.io ..."
  docker login -u "$QUAY_USERNAME" -p "$QUAY_PASSWORD" quay.io
}

publish_docker_image() {
  echo ">>> Publishing the operator docker image ..."
  docker push ${repo}:latest
  docker push ${repo}:${major_version}
  docker push ${repo}:${release_tag}
}

build_docker_image
login_to_quay_io
publish_docker_image
