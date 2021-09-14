# Releasing Splunk OpenTelemetry Python


This document explains the steps required to publish a new release of splunk-opentelemetry Python package to PYPI.

Release process:

1. [Checkout a release branch](#1-checkout-a-release-branch)
2. [Update version number and changelog](#2-update-the-version-number)
3. [Submit PR for review and merge to main](#3-submit-changes-for-review)
4. [Create a new Github Release](#4-create-a-draft-github-release)
5. [Create and push tag](#5-create-and-publish-a-version-git-tag)
6. [Verify CircleCI and PYPI](#6-verify-circleci-job-and-pypi-package)
7. [Publish the draft GitHub Release](#7-publish-the-draft-github-release)


## 1. Checkout a release branch

Checkout a new branch from main with name equal to `release/v<VERSION_NUMBER>`.
So if you intent to release `1.2.0`, create a branch named `release/v1.2.0`

## 2. Update the version number

Update version in `pyproject.toml`.

In CHANGELOG.md, rename `Unreleased` header with the new version and today's date.
Add a new empty `Unreleased` section at top.

## 3. Submit changes for review

Commit the changes and submit them for review.
The commit title should be `Release v<VERSION_NUMBER>` and the description should be all the changes,
additions and deletions this versions will ship. This can be copied as is from the CHANGELOG file.
Merge the PR back to main once it is approved. 

## 4. Create a draft GitHub Release

Go to the (project on Github)[https://github.com/signalfx/splunk-otel-js] and create a new release.
On top of the release notes mention the version of OpenTelemetry API and other packages this
version depends on. Do this for every release, even if the OpenTelemetry version has not changed.

Next copy the changes, additions and deletions this version contains from the CHANGELOG file.

Release name should be exact version number without the prefix `v` we use elsewhere.

Save the release as a draft.

## 5. Create and publish a version git tag

Switch to `main` branch and pull the latest changes. Make sure your git head is on the release commit.
Switch to the commit if it is not. 

Create a new git tag for the release with the `v` prefix. For example, if you're releasing `1.2.0`:

```
git tag v1.2.0
git push origin v1.2.0
```

## 6. Verify CircleCI job and PYPI package

Go to (the CircleCI project)[https://app.circleci.com/pipelines/github/signalfx/splunk-otel-python] and verify the build for your new version was successful.

Go to (https://pypi.org/project/splunk-opentelemetry/)[https://pypi.org/project/splunk-opentelemetry/] and verify the new package was published. It may take a few minutes for the web interface to reflect the new package but it should be installable instantly. 

Navigate to examples/falcon, upgrade `splunk-opentelemetry` package to the new version and verify it is working as expected. If you're feeling like doing some more work, commit the changes to the example falcon app and submit a PR.

## 7. Publish the draft GitHub Release

Pull up the draft GitHub Release you created earlier in step 4 and publish it. 