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

from abc import ABC, abstractmethod
from os import environ
from typing import Dict, Optional


# A base class to abstract environment variable i/o.
class _EnvLoaderABC(ABC):
    @abstractmethod
    def get(self, name: str, default: Optional[any] = None):
        pass

    @abstractmethod
    def set(self, name: str, value: str):
        pass

    @abstractmethod
    def set_if_unset(self, name: str, value: str):
        pass

    @abstractmethod
    def set_all_unset(self, pairs: Dict):
        pass


# The standard/production implementation for reading from and writing to environment variables.
class _OSEnvLoader(_EnvLoaderABC):
    def get(self, name, default: Optional[any] = None):
        return environ.get(name, default)

    def set(self, name, value):
        environ[name] = value

    def set_all_unset(self, pairs: Dict):
        for name, value in pairs.items():
            self.set_if_unset(name, value)

    def set_if_unset(self, name: str, value: str):
        if name not in environ:
            environ[name] = value

