#!/usr/bin/env bash
set -e

cd docker

release_tag="$1" # e.g. v1.2.3

stable_release_regex='^v[0-9]+\.[0-9]+\.[0-9]+$'
prerelease_regex='^v[0-9]+\.[0-9]+\.[0-9]+-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*$'

if [[ ! "$release_tag" =~ $stable_release_regex && ! "$release_tag" =~ $prerelease_regex ]]; then
  echo "ERROR: release tag must match v<major>.<minor>.<patch> or v<major>.<minor>.<patch>-<prerelease>"
  exit 1
fi

is_stable_release() {
  [[ "$release_tag" =~ $stable_release_regex ]]
}

if [ -z "${CI_COMMIT_TAG:-}" ]; then
  echo "ERROR: CI_COMMIT_TAG is required"
  exit 1
fi

if [ "$CI_COMMIT_TAG" != "$release_tag" ]; then
  echo "ERROR: release tag argument does not match CI_COMMIT_TAG"
  exit 1
fi

if [ "${CI_COMMIT_REF_PROTECTED:-}" != "true" ]; then
  echo "ERROR: publishing is only allowed from protected refs"
  exit 1
fi

major_version=$(echo $release_tag | cut -d '.' -f1) # e.g. "v1"
repo="quay.io/signalfx/splunk-otel-instrumentation-python"
image_name="splunk-otel-instrumentation-python"
secureapp_image_name="splunk-otel-instrumentation-python-secureapp"

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

build_docker_image() {
  echo ">>> Building the operator docker image ..."
  docker build \
    --build-arg REQUIREMENTS_FILE=requirements.txt \
    -t "${image_name}" .
  if is_stable_release; then
    docker tag "${image_name}" "${repo}:latest"
    docker tag "${image_name}" "${repo}:${major_version}"
  fi
  docker tag "${image_name}" "${repo}:${release_tag}"

  echo ">>> Building the SecureApp operator docker image ..."
  docker build \
    --build-arg REQUIREMENTS_FILE=requirements-secureapp.txt \
    --build-arg VERIFY_SECUREAPP=true \
    -t "${secureapp_image_name}" .
  if is_stable_release; then
    docker tag "${secureapp_image_name}" "${repo}:latest-secureapp"
    docker tag "${secureapp_image_name}" "${repo}:${major_version}-secureapp"
  fi
  docker tag "${secureapp_image_name}" "${repo}:${release_tag}-secureapp"
}

login_to_quay_io() {
  echo ">>> Logging into quay.io ..."
  docker login -u "$QUAY_USERNAME" -p "$QUAY_PASSWORD" quay.io
}

publish_docker_image() {
  echo ">>> Publishing the operator docker image ..."
  if is_stable_release; then
    docker push "${repo}:latest"
    docker push "${repo}:${major_version}"
  fi
  docker push "${repo}:${release_tag}"

  echo ">>> Publishing the SecureApp operator docker image ..."
  if is_stable_release; then
    docker push "${repo}:latest-secureapp"
    docker push "${repo}:${major_version}-secureapp"
  fi
  docker push "${repo}:${release_tag}-secureapp"
}

check_package_available
build_docker_image
login_to_quay_io
publish_docker_image
