#!/usr/bin/env python

import os
import os.path
import sys
from argparse import REMAINDER, ArgumentParser
from logging import getLogger
from os import environ, execl, getcwd
from shutil import which

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
ap.add_argument("command", help="Your Python application.")
ap.add_argument(
    "command_args",
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

    executable = which(args.command)
    execl(executable, args.command, *args.command_args)
