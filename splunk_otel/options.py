# Copyright 2021 Splunk Inc.
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
from os import environ
from typing import Optional

logger = logging.getLogger("options")


def from_env(name: str, default: Optional[str] = None) -> Optional[str]:
    old_key = "SPLK_{0}".format(name)
    new_key = "SPLUNK_{0}".format(name)
    if old_key in environ:
        logger.warning(
            "%s is deprecated and will be removed soon. Please use %s instead",
            old_key,
            new_key,
        )
        return environ[old_key]
    return environ.get(new_key, default)
