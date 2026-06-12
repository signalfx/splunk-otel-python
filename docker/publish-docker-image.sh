#!/usr/bin/env bash
set -e

cd docker

release_tag="$1" # e.g. v1.2.3 or v1.2.3-rc.1

stable_release_regex='^v([0-9]+\.[0-9]+\.[0-9]+)$'
prerelease_regex='^v([0-9]+\.[0-9]+\.[0-9]+)-(alpha|beta|rc)\.(0|[1-9][0-9]*)$'

if [[ "$release_tag" =~ $stable_release_regex ]]; then
  package_version="${BASH_REMATCH[1]}"
elif [[ "$release_tag" =~ $prerelease_regex ]]; then
  base_version="${BASH_REMATCH[1]}"
  prerelease_phase="${BASH_REMATCH[2]}"
  prerelease_number="${BASH_REMATCH[3]}"
  case "$prerelease_phase" in
    alpha) package_version="${base_version}a${prerelease_number}" ;;
    beta) package_version="${base_version}b${prerelease_number}" ;;
    rc) package_version="${base_version}rc${prerelease_number}" ;;
  esac
else
  echo "ERROR: release tag must match v<major>.<minor>.<patch> or v<major>.<minor>.<patch>-(alpha|beta|rc).<number>"
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

  echo "Waiting for $package_name==$package_version to be available on PyPI..."

  for i in $(seq 1 $max_attempts); do
      if curl --silent --fail "https://pypi.org/pypi/$package_name/$package_version/json" > /dev/null; then
          echo "Package $package_name==$package_version is available on PyPI."
          break
      fi
      echo "Attempt $i: Package not yet available. Retrying in $sleep_seconds seconds..."
      sleep $sleep_seconds
  done

  if [ "$i" -eq "$max_attempts" ]; then
      echo "ERROR: Package $package_name==$package_version was not found on PyPI after $max_attempts attempts."
      exit 1
  fi
}

check_about_version() {
  version_file="../src/splunk_otel/__about__.py"
  expected_version_line="__version__ = \"${package_version}\""

  if ! grep -qxF "$expected_version_line" "$version_file"; then
    echo "ERROR: $version_file must contain $expected_version_line"
    exit 1
  fi
}

check_requirements_pin() {
  expected_requirement="splunk-opentelemetry==${package_version}"

  if ! grep -qxF "$expected_requirement" requirements.txt; then
    echo "ERROR: requirements.txt must contain $expected_requirement"
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

check_about_version
check_requirements_pin
check_package_available
build_docker_image
login_to_quay_io
publish_docker_image
