# Releasing Splunk OpenTelemetry Python


This document explains the steps required to publish a new release of splunk-opentelemetry Python package to PYPI.

We'll pretend to release version 1.1.0

Release process:

1. [Checkout a release branch](#1-checkout-a-release-branch)
2. [Submit PR for review and merge to main](#3-submit-changes-for-review)
3. [Release the package](#4-create-a-draft-github-release)
4. [Create and push tag](#5-create-and-publish-a-version-git-tag)
5. [Verify CircleCI and PYPI](#6-verify-circleci-job-and-pypi-package)
6. [Publish the draft GitHub Release](#7-publish-the-draft-github-release)


## 1. Prepare the release branch

Run the following command to prepare the release branch assuming we want to release version 1.1.0

```
make prepare-release VERSION=1.1.0
```

This will create a new branch `release/v1.1.0`, bump the package version to `1.1.0`, update the changelog file and
update all documentation references to point to the new version.

## 2. Submit changes for review

Push the new branch `release/v1.1.0` to Github and create a PR. The PR title should be `Release v<VERSION_NUMBER>`
and the description should be all the changes, additions and deletions this versions will ship.
This can be copied as is from the CHANGELOG file. Merge the PR back to main once it is approved. 

## 3. Release the new package

Switch to `main` branch and pull the latest changes. Make sure your git head is on the release commit.
Switch to the commit if it is not. 

Create a new git tag for the release with the `v` prefix. For example, if you're releasing `1.1.0`:

```
git tag v1.1.0
```

Push the tag to the Gitlab releaser project (not Github).

```
git push gitlab v1.1.0
```

## 4. Monitor Gitlab release job 

Go to (the Gitlab project)[https://cd.splunkdev.com/o11y-gdi/splunk-otel-python-releaser/-/pipelines] and verify the build for your new version was successful.

This CI job will automatically create a Github release with changelogs and artifacts, and also publish new version to PyPI.


## 5. Verify release

- Go to the Gitlab Splunk Otel Python releaser project and verify the new GH release was created and all artifacts were uploaded.

- Go to (https://pypi.org/project/splunk-opentelemetry/)[https://pypi.org/project/splunk-opentelemetry/] and verify the new package was published. It may take a few minutes for the web interface to reflect the new package but it should be installable instantly. 

- Download checksums.txt from the GH release and ensure they match the checksums from pypi.org for each artifact.

## 6. Test new release

Navigate to examples/falcon, upgrade `splunk-opentelemetry` package to the new version and verify it is working as expected. If you're feeling like doing some more work, commit the changes to the example falcon app and submit a PR.
