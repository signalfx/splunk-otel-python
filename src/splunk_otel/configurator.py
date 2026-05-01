#  Copyright Splunk Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from opentelemetry.sdk._configuration import _OTelSDKConfigurator

from splunk_otel.callgraphs import configure_callgraphs
from splunk_otel.config_provider import ConfigProvider, get_config_provider
from splunk_otel.env import Env
from splunk_otel.profile import start_profiling

if TYPE_CHECKING:
    from typing_extensions import Self


class SplunkConfigurator(_OTelSDKConfigurator):
    _local_instance: ClassVar[SplunkConfigurator | None] = None

    # The upstream singleton __new__ forwards constructor args to object.__new__,
    # so keep a local version that supports our optional args.
    def __new__(
        cls,
        *_args,
        **_kwargs,
    ) -> Self:
        instance = cls._local_instance
        if instance is None:
            instance = object.__new__(cls)
            cls._local_instance = instance
        return instance

    def __init__(self, config_provider: ConfigProvider | None = None):
        self.config_provider = config_provider or get_config_provider(Env())

    def _configure(self, **kwargs):
        super()._configure(**kwargs)

        if self.config_provider.profiler_enabled():
            start_profiling(
                self.config_provider.service_name(),
                self.config_provider.profiler_call_stack_interval(),
            )
        if self.config_provider.snapshot_profiler_enabled():
            configure_callgraphs(
                self.config_provider.service_name(),
                self.config_provider.snapshot_sampling_interval(),
            )
