# Copyright Splunk Inc.
# SPDX-License-Identifier: Apache-2.0

from contextlib import suppress
from logging import getLogger


class DiagnosticLogger:
    def __init__(self, name: str) -> None:
        self._logger = getLogger(name)

    def exception(self, message: str) -> None:
        # A diagnostic failure must not interrupt application code.
        with suppress(Exception):
            self._logger.exception(message, stacklevel=2)
