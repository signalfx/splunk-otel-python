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

import subprocess
from os import path

import click
import keepachangelog
from github_release import gh_release_create

root = path.dirname(path.abspath(path.dirname(__file__)))
pyproject_path = path.join(root, "pyproject.toml")
changelog_path = path.join(root, "CHANGELOG.md")
relase_template_path = path.join(root, "scripts", "gh_release_template.md")
artifacts_path = path.join(root, "dist/*")


def _get_package_version(package):
    return (
        subprocess.check_output(
            ["poetry", "show", package], cwd=root, universal_newlines=True
        )
        .split("\n")[1]
        .split()[2]
    )


def _get_otel_versions():
    return {
        "api": _get_package_version("opentelemetry-api"),
        "sdk": _get_package_version("opentelemetry-sdk"),
        "instrumentation": _get_package_version("opentelemetry-instrumentation"),
    }


def _get_version() -> str:
    return subprocess.check_output(
        ["poetry", "version"], cwd=root, universal_newlines=True
    ).split()[1]


def _render_changelog(version):
    return keepachangelog.to_raw_dict(changelog_path).get(version, {}).get("raw", "")


def _render_release_notes(**kwargs):
    with open(relase_template_path, "r") as tmpl:
        notes = tmpl.read().format(**kwargs)
        return notes


def _print_release_details(**kwargs):
    print(
        """
Run with --dry-run=false to create the following release

- Repo: {repo_name}
- Version: {tag_name}
- Name: {name}
- Artifacts: {asset_pattern}
- Release notes:

{body}
""".format(
            **kwargs
        )
    )


@click.command()
@click.option(
    "--dry-run",
    default=True,
    help="Print out the release details instead of actually creating one",
)
def main(dry_run):
    version = _get_version()
    otel_versions = _get_otel_versions()

    changelog = _render_changelog(version)
    release_notes = _render_release_notes(
        version=version,
        api_version=otel_versions["api"],
        sdk_version=otel_versions["sdk"],
        instrumentation_version=otel_versions["instrumentation"],
        changelog=changelog,
    )

    git_tag = "v{}".format(version)

    action = _print_release_details
    if not dry_run:
        action = gh_release_create
    action(
        repo_name="signalfx/splunk-otel-python",
        tag_name=git_tag,
        publish=True,
        name=version,
        body=release_notes,
        asset_pattern=artifacts_path,
    )


if __name__ == "__main__":
    main()  # pylint: disable=E1120
