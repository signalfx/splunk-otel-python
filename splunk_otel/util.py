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

import logging
import os
from typing import Any, Optional


def _get_log_level(level):
    levels = {
        "none": logging.NOTSET,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "fatal": logging.CRITICAL,
    }

    return levels[level.lower()]


def _init_logger(name):
    level = _get_log_level(os.environ.get("OTEL_LOG_LEVEL", "info"))
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(logging.StreamHandler())


def _is_truthy(value: Any) -> bool:
    if isinstance(value, str):
        value = value.lower().strip()
    return value in [True, 1, "true", "yes"]


def _is_truthy_str(value: Optional[str]) -> bool:
    if not value:
        return False

    return value.strip().lower() not in (
        "false",
        "no",
        "f",
        "0",
    )
