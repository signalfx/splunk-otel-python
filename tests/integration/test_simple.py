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

import subprocess

from requests_futures.sessions import FuturesSession

from .conftest import IntegrationSession


def test_simple_app(integration: IntegrationSession):
    session = FuturesSession()
    # start polling collector for spans
    future = session.get(integration.poll_url)

    # execute instrumented program
    subprocess.call(
        ["python", "{0}/simple/main.py".format(integration.rootdir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # get result of poll and assert spans
    response = future.result()
    assert response.ok
    spans = response.json()
    assert len(spans) == 1
    span = spans[0]

    assert span["operationName"] == "custom span"
    assert span["tags"] == [
        {"key": "otel.library.name", "vStr": "simple"},
        {"key": "otel.library.version", "vStr": "0.1"},
        {"key": "span.kind", "vStr": "internal"},
        {"key": "status.code", "vType": "INT64"},
    ]
