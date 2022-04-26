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

import os
import subprocess

from requests_futures.sessions import FuturesSession

from .conftest import IntegrationSession


def _test_simple(integration: IntegrationSession, exporter: str):
    session = FuturesSession()
    # start polling collector for spans
    future = session.get(integration.poll_url)

    # execute instrumented program
    env = os.environ.copy()
    env["OTEL_TRACES_EXPORTER"] = exporter
    subprocess.check_call(
        ["python", f"{integration.rootdir}/simple/main.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )

    # get result of poll and assert spans
    response = future.result()
    assert response.ok
    spans = response.json()
    assert len(spans) == 1
    span = spans[0]

    assert span["operationName"] == "custom span"

    tags = [
        {"key": "otel.library.name", "vStr": "simple"},
        {"key": "otel.library.version", "vStr": "0.1"},
    ]
    for tag in tags:
        assert tag in span["tags"]


def test_otlp_simple(integration: IntegrationSession):
    _test_simple(integration, exporter="otlp")


def test_jaeger_simple(integration: IntegrationSession):
    _test_simple(integration, exporter="jaeger-thrift-splunk")
