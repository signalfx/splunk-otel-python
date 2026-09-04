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
image_platforms="linux/amd64,linux/arm64"

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

  if ! grep -qxE 'secureapp-python-agent==[^[:space:]]+' requirements-secureapp.txt; then
    echo "ERROR: requirements-secureapp.txt must pin secureapp-python-agent with =="
    exit 1
  fi
}

build_docker_image() {
  local requirements_file="$1"
  shift

  docker buildx build \
    --platform "${image_platforms}" \
    --build-arg "REQUIREMENTS_FILE=${requirements_file}" \
    "$@" \
    --provenance=false \
    --output type=cacheonly \
    .
}

build_docker_images() {
  echo ">>> Building the standard operator Docker image for ${image_platforms} ..."
  build_docker_image requirements.txt

  echo ">>> Building the SecureApp operator Docker image for ${image_platforms} ..."
  build_docker_image requirements-secureapp.txt --build-arg VERIFY_SECUREAPP=true
}

build_and_publish_standard_docker_image() {
  local tag_arguments=(--tag "${repo}:${release_tag}")
  if is_stable_release; then
    tag_arguments+=(--tag "${repo}:latest")
    tag_arguments+=(--tag "${repo}:${major_version}")
  fi

  echo ">>> Publishing the standard operator Docker image for ${image_platforms} ..."
  docker buildx build \
    --platform "${image_platforms}" \
    --build-arg REQUIREMENTS_FILE=requirements.txt \
    "${tag_arguments[@]}" \
    --provenance=false \
    --push \
    .
}

build_and_publish_secureapp_docker_image() {
  local tag_arguments=(--tag "${repo}:${release_tag}-secureapp")
  if is_stable_release; then
    tag_arguments+=(--tag "${repo}:latest-secureapp")
    tag_arguments+=(--tag "${repo}:${major_version}-secureapp")
  fi

  echo ">>> Publishing the SecureApp operator Docker image for ${image_platforms} ..."
  docker buildx build \
    --platform "${image_platforms}" \
    --build-arg REQUIREMENTS_FILE=requirements-secureapp.txt \
    --build-arg VERIFY_SECUREAPP=true \
    "${tag_arguments[@]}" \
    --provenance=false \
    --push \
    .
}

login_to_quay_io() {
  echo ">>> Logging into quay.io ..."
  docker login -u "$QUAY_USERNAME" -p "$QUAY_PASSWORD" quay.io
}

check_about_version
check_requirements_pin
check_package_available
build_docker_images
login_to_quay_io
build_and_publish_standard_docker_image
build_and_publish_secureapp_docker_image
