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

import argparse
import pkgutil
import subprocess
import sys
from logging import getLogger
from typing import Any, Callable, Collection, Dict, Optional

from opentelemetry.instrumentation.bootstrap import instrumentations
from opentelemetry.instrumentation.bootstrap import run as otel_run

from splunk_otel import symbols
from splunk_otel.version import format_version_info

logger = getLogger(__file__)


def run() -> None:
    action_install = "install"
    action_requirements = "requirements"

    parser = argparse.ArgumentParser(
        description="""
        opentelemetry-bootstrap detects installed libraries and automatically
        installs the relevant instrumentation packages for them.
        """
    )
    parser.add_argument(
        "--version",
        "-v",
        required=False,
        action="store_true",
        dest="version",
        help="Print version information",
    )
    parser.add_argument(
        "-a",
        "--action",
        choices=[
            action_install,
            action_requirements,
        ],
        help="""
        install - uses pip to install the new requirements using to the
                  currently active site-package.
        requirements - prints out the new requirements to stdout. Action can
                       be piped and appended to a requirements.txt file.
        """,
    )
    args = parser.parse_args()

    if args.version:
        print(format_version_info())
        return

    # pass custom list to otel_run() once otel supports receiving custom args
    # instead of modifying sys.argv
    if not args.action:
        sys.argv.append("--action=install")
    otel_run()
