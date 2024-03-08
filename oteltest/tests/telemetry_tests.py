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
import json
from pathlib import Path

import pytest

from oteltest.common import Request, Telemetry

fixture_path = Path(__file__).parent / "fixtures"


@pytest.fixture
def telemetry_fixture():
    with open(str(fixture_path / "telemetry.json")) as file:
        telemetry_dict = json.loads(file.read())
        return Telemetry(
            trace_reqs=[Request(**req) for req in telemetry_dict["trace_reqs"]],
            log_reqs=[Request(**req) for req in telemetry_dict["log_reqs"]],
            metric_reqs=[Request(**req) for req in telemetry_dict["metric_reqs"]],
        )


def test_telemetry(telemetry_fixture):
    assert telemetry_fixture.has_header("x-sf-token", "abc123")
