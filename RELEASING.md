# Releasing splunk-opentelemetry

How to release a new version of the `splunk-opentelemetry` project:

1) Create a new branch from `main`
2) Bump dependency versions in pyproject.toml
    - update otel dependencies to the latest versions, e.g.:
        - `"opentelemetry-exporter-otlp-proto-http==1.36.0"`
        - `"opentelemetry-instrumentation==0.57b0"`
3) Bump our version in __about__.py
4) Update additional version string locations
    - `ott_lib.py` # this file is used as a library for integration tests
    - `docker/requirements.txt` # this file is used to build the docker init image for the operator
    - `docker/example-instrumentation.yaml`  # this file is just an example but would be nice to show the latest version
5) Add a new entry in CHANGELOG.md
6) Commit the changes with a message like "Bump version to 3.4.5"
    - you may want to use multiple commits for clarity, e.g.:
        - bump dependency versions
        - bump our version in `__about__.py`
        - update additional version string locations
        - update CHANGELOG.md
7) Push the changes to the Github Splunk OTel Python repo
8) Open a PR and merge after approval
9) Navigate to the GitLab mirror and verify that the mirror has pulled the version you just merged by checking the
   version number in the `__about__.py` file
10) When ready to release, create a new tag like `v3.4.5` on main in GitLab
    - a tag of the format `vX.Y.Z` will trigger the CI pipeline to build and publish the package to PyPI and the Docker
      image to Quay
11) Monitor the release pipeline in GitLab to ensure it completes successfully
12) Post release, verify that the new package is available on PyPI and the Docker image is available on Quay
13) Smoke test the release locally by installing the new package and running it with a small app
14) Navigate to Pipelines in the GitLab repo, click the download button for the build job that just ran,
    and select the 'build-job' artifact
    - this will download a tarball of the package files
15) Navigate to the Splunk OTel Python repo and create a New Release
    - create a new tag on publish with the tag name you created in step 10
    - set the title to that tag name (e.g. `v2.7.0`)
    - unpack the tarball from step 14 and drag its contents onto the attachments section of the New Release page
    - Leave the defaults selected and click Publish
