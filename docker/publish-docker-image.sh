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

check_package_available() {
  package_name="splunk-opentelemetry"
  max_attempts=10
  sleep_seconds=10

  echo "Waiting for $package_name==$release_tag to be available on PyPI..."

  for i in $(seq 1 $max_attempts); do
      if curl --silent --fail "https://pypi.org/pypi/$package_name/$release_tag/json" > /dev/null; then
          echo "Package $package_name==$release_tag is available on PyPI."
          break
      fi
      echo "Attempt $i: Package not yet available. Retrying in $sleep_seconds seconds..."
      sleep $sleep_seconds
  done

  if [ "$i" -eq "$max_attempts" ]; then
      echo "ERROR: Package $package_name==$release_tag was not found on PyPI after $max_attempts attempts."
      exit 1
  fi
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
check_package_available
login_to_quay_io
publish_docker_image
