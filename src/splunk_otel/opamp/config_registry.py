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

"""
Config registry for OpAMP EffectiveConfig reporting (and eventually remote updates).

Feature modules register the keys they own at startup. OpAMP reads all registered
values when building EffectiveConfig, and will call write callbacks for remote
config updates in Phase 2.

Usage:
    registry = ConfigRegistry()

    # in profile.py
    registry.register("SPLUNK_PROFILER_ENABLED", getter=lambda: str(ctx.running))

    # in opamp/__init__.py
    registry.get_all()  # -> {"SPLUNK_PROFILER_ENABLED": "true", ...}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class _ConfigEntry:
    getter: Callable[[], str | None]
    setter: Callable[[str], None] | None = None


class ConfigRegistry:
    def __init__(self):
        self._entries: dict[str, _ConfigEntry] = {}

    def register(
        self,
        key: str,
        *,
        getter: Callable[[], str],
        setter: Callable[[str], None] | None = None,
    ) -> None:
        """
        Register a config key with read (and optionally write) callbacks.

        Args:
            key: The config key name (e.g. "SPLUNK_PROFILER_ENABLED")
            getter: Returns the current string value of this key.
            setter: Applies an updated string value. None means read-only (restart required).
        """
        self._entries[key] = _ConfigEntry(getter=getter, setter=setter)

    def get_all(self) -> dict[str, str]:
        """Return current values for all registered keys, omitting keys whose getter returns None."""
        out = {}
        for key, entry in self._entries.items():
            try:
                val = entry.getter()
                if val is not None:
                    out[key] = val
            except Exception:  # noqa: BLE001
                logger.warning("Failed to read config key %s", key, exc_info=True)
        return out

    def update(self, updates: dict[str, str]) -> list[str]:
        """
        Update registry with a dict of keys to values.
        """
        updated_keys = []
        for key, value in updates.items():
            entry = self._entries.get(key)
            if entry is None:
                logger.warning("Ignoring unknown config key: %s", key)
                continue
            if entry.setter is None:
                logger.warning("Ignoring read-only config key: %s", key)
                continue
            try:
                entry.setter(value)
                updated_keys.append(key)
                logger.info("Applied config update: %s=%s", key, value)
            except Exception:
                logger.exception("Failed to apply config key %s=%s", key, value)
        return updated_keys
