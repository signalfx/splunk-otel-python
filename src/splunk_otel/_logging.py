# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

from contextlib import suppress
from logging import Logger


def log_exception(logger: Logger, message: str) -> None:
    # A failing log handler can interrupt span callbacks or stop the sampler.
    with suppress(Exception):
        logger.exception(message, stacklevel=2)
