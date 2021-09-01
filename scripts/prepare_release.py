# Copyright Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from datetime import datetime
from os import path

import click
from splunk_packaging import bump_version, changelog_path, get_versions, root_path

readme_path = path.join(root_path, "README.md")
otel_badge_span = (
    '<span class="otel-version-badge">'
    '<a href="https://github.com/open-telemetry/opentelemetry-python/releases/tag/v{0}">'
    '<img alt="OpenTelemetry Python Version" '
    'src="https://img.shields.io/badge/otel-{0}-blueviolet?style=for-the-badge"/>'
    "</a></span>"
)
docs_version_span = (
    '<span class="docs-version-header">The documentation below refers to the '
    "in development version of this package. Docs for the latest version "
    "([v{0}](https://github.com/signalfx/splunk-otel-python/releases/tag/v{0})) "
    "can be found [here](https://github.com/signalfx/splunk-otel-python/blob"
    "/v{0}/README.md).</span>"
)
splunk_version_span = '<span class="splunk-version">{0}</span>'
otel_api_version_span = '<span class="otel-api-version">{0}</span>'
otel_sdk_version_span = '<span class="otel-sdk-version">{0}</span>'
otel_instrumentation_version_span = (
    '<span class="otel-instrumentation-version">{0}</span>'
)
regexp = '<span class="{0}">.*</span>'


def update_docs(versions):
    variables = {
        "splunk-version": splunk_version_span.format(versions.distro),
        "otel-api-version": otel_api_version_span.format(versions.api),
        "otel-sdk-version": otel_sdk_version_span.format(versions.sdk),
        "otel-instrumentation-version": otel_instrumentation_version_span.format(
            versions.instrumentation
        ),
        "docs-version-header": docs_version_span.format(versions.distro),
        "otel-version-badge": otel_badge_span.format(versions.sdk),
    }

    markdown = ""
    with open(readme_path, "r", encoding="utf-8") as readme:
        markdown = readme.read()

    for name, value in variables.items():
        markdown = re.sub(regexp.format(name), value, markdown)

    with open(readme_path, "w", encoding="utf-8") as readme:
        readme.write(markdown)


def update_changelog(file_path, version):
    release_title = "## {0} - {1}".format(version, datetime.today().strftime("%Y-%m-%d"))
    with open(file_path, "r+", encoding="utf-8") as file:
        modified = file.read().replace(
            "## Unreleased", "## Unreleased\n\n{0}".format(release_title), 1
        )
        file.seek(0)
        file.write(modified)


@click.command()
@click.option(
    "--version",
    help="New version number that you'd like to release",
)
def main(version):
    bump_version(version)
    versions = get_versions()
    update_docs(versions)
    update_changelog(changelog_path, versions.distro)


if __name__ == "__main__":
    main()  # pylint: disable=E1120
