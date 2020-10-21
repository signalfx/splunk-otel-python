#!/usr/bin/env python

import os
import os.path
import sys
from argparse import REMAINDER, ArgumentParser
from logging import getLogger
from os import environ, execl, getcwd
from shutil import which

from splunk_otel.version import format_version_info

logger = getLogger(__file__)

ap = ArgumentParser()
ap.add_argument(
    "--token",
    "-t",
    required=False,
    type=str,
    dest="token",
    help="Your SignalFx Access Token (SIGNALFX_ACCESS_TOKEN env var by default)",
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


def run():
    args = ap.parse_args()
    if args.token:
        logger.warn("--token is not support yet and will have no effect.")
        os.environ["SIGNALFX_ACCESS_TOKEN"] = args.token

    site_dir = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "site",
    )
    py_path = os.environ.get("PYTHONPATH", "")

    # This is being added to support applications that are being run from their
    # own executable, like Django.
    if not py_path:
        py_path = []
    else:
        py_path = py_path.split(os.path.pathsep)
    cwd_path = getcwd()
    if cwd_path not in py_path:
        py_path.insert(0, cwd_path)
    py_path = os.path.pathsep.join(py_path)

    os.environ["PYTHONPATH"] = site_dir + os.pathsep + py_path if py_path else site_dir

    if args.version:
        print(format_version_info())
        return

    if not args.command:
        ap.error(ap.format_help())

    cmd, cmd_args = args.command[0], args.command[1:]
    executable = which(cmd)
    try:
        execl(executable, cmd, *cmd_args)
    except TypeError:
        logger.error("failed to execute program: %s", " ".join(args.command))
        raise
