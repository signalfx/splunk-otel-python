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

from typing import Optional

from opentelemetry.trace import status

# pylint: disable=protected-access


def status_init(
    self: status.Status,
    status_code: status.StatusCode = status.StatusCode.UNSET,
    description: Optional[str] = None,
) -> None:
    """This method replaces Otel Status's __init__ method.
    It is identical to the method it replaces except that it does not
    log warnings when description is used with a non-error status code.

    TODO: Remove after upgrading to opentelemetry-python 1.3
    """
    self._status_code = status_code
    self._description = None

    if description:
        if not isinstance(description, str):
            status.logger.warning("Invalid status description type, expected str")
            return
        if status_code is not status.StatusCode.ERROR:
            return

    self._description = description


def _apply() -> None:
    if not hasattr(status.Status, "__init__orig__"):
        status.Status.__init_orig__ = status.Status.__init__  # type: ignore
        status.Status.__init__ = status_init  # type: ignore
