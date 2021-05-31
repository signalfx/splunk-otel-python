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
from collections import namedtuple
from os import path

Versions = namedtuple("Versions", ("api", "sdk", "instrumentation", "distro"))

root_path = path.dirname(path.abspath(path.dirname(__file__)))
changelog_path = path.join(root_path, "CHANGELOG.md")


def bump_version(version):
    subprocess.run(["poetry", "version", version], cwd=root_path, check=True)


def get_package_version(package):
    return (
        subprocess.check_output(
            ["poetry", "show", package], cwd=root_path, universal_newlines=True
        )
        .split("\n")[1]
        .split()[2]
    )


def get_distro_version() -> str:
    return subprocess.check_output(
        ["poetry", "version"], cwd=root_path, universal_newlines=True
    ).split()[1]


def get_versions():
    return Versions(
        api=get_package_version("opentelemetry-api"),
        sdk=get_package_version("opentelemetry-sdk"),
        instrumentation=get_package_version("opentelemetry-instrumentation"),
        distro=get_distro_version(),
    )
