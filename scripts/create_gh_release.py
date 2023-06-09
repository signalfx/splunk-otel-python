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

from os import path
from time import sleep
from urllib3.exceptions import HTTPError

import backoff
import click
import keepachangelog
from github_release import gh_release_create
from splunk_packaging import changelog_path, get_versions, root_path

relase_template_path = path.join(root_path, "scripts", "gh_release_template.md.in")
artifacts_path = path.join(root_path, "dist/*")


def render_changelog(version):
    return keepachangelog.to_raw_dict(changelog_path).get(version, {}).get("raw", "")


def render_release_notes(**kwargs):
    with open(relase_template_path, "r", encoding="utf-8") as tmpl:
        notes = tmpl.read().format(**kwargs)
        return notes


def print_release_details(**kwargs):
    print(
        f"""
Run with --dry-run=false to create the following release

- Repo: {kwargs["repo_name"]}
- Version: {kwargs["tag_name"]}
- Name: {kwargs["name"]}
- Artifacts: {kwargs["asset_pattern"]}
- Release notes:

{kwargs["body"]}
"""
    )


@click.command()
@click.option(
    "--dry-run",
    default=True,
    help="Print out the release details instead of actually creating one",
)
@backoff.on_exception(backoff.expo,
    HTTPError,
    max_time=60)
def main(dry_run):
    versions = get_versions()

    changelog = render_changelog(versions.distro)
    release_notes = render_release_notes(
        version=versions.distro,
        api_version=versions.api,
        sdk_version=versions.sdk,
        instrumentation_version=versions.instrumentation,
        changelog=changelog,
    )

    git_tag = f"v{versions.distro}"

    action = print_release_details
    if not dry_run:
        action = gh_release_create
    sleep(5)
    action(
        repo_name="signalfx/splunk-otel-python",
        tag_name=git_tag,
        publish=True,
        name=versions.distro,
        body=release_notes,
        asset_pattern=artifacts_path,
    )


if __name__ == "__main__":
    main()  # pylint: disable=E1120
