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

from opentelemetry.metrics import get_meter_provider
from opentelemetry.sdk.metrics import MeterProvider

logger = logging.getLogger(__name__)


def start_metrics() -> MeterProvider:
    # FIXME mark deprecated and/or log warning
    return get_meter_provider()
