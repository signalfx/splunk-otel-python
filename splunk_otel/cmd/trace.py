#!/usr/bin/env python

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


import os
import os.path
import sys
from argparse import REMAINDER, ArgumentParser
from logging import getLogger
from os import environ, execl, getcwd
from shutil import which
from typing import List, Union

from opentelemetry.instrumentation.auto_instrumentation import run as otel_run

from splunk_otel.version import format_version_info

logger = getLogger(__file__)

ap = ArgumentParser()
ap.add_argument(
    "--token",
    "-t",
    required=False,
    type=str,
    dest="token",
    help="Your Splunk Access Token (SPLUNK_ACCESS_TOKEN env var by default)",
)
ap.add_argument(
    "--service-name",
    "-s",
    required=False,
    type=str,
    dest="service_name",
    help="The service name that should be passed to a tracer provider.",
)
ap.add_argument(
    "--version",
    "-v",
    required=False,
    action="store_true",
    dest="version",
    help="Print version information",
)
ap.add_argument(
    "command",
    help="Arguments for your application.",
    nargs=REMAINDER,
)


def run() -> None:
    args = ap.parse_args()
    if args.version:
        print(format_version_info())
        return

    if args.token:
        os.environ["SPLUNK_ACCESS_TOKEN"] = args.token

    if args.service_name:
        os.environ["SPLUNK_SERVICE_NAME"] = args.service_name

    if not args.command:
        ap.error(ap.format_help())

    try:
        otel_run()
    except TypeError:
        logger.error("failed to execute program: %s", " ".join(args.command))
        raise
