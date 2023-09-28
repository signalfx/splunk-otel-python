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

from collections import namedtuple
from os import path

import pytest
import requests

IntegrationSession = namedtuple("Session", ("poll_url", "rootdir"))


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return path.join(
        str(pytestconfig.rootdir), "tests", "integration", "docker-compose.yml"
    )


@pytest.fixture(scope="session")
def integration(pytestconfig, docker_ip, docker_services):
    port = docker_services.port_for("collector", 13133)
    url = f"http://{docker_ip}:{port}"
    docker_services.wait_until_responsive(
        timeout=10, pause=0.1, check=lambda: is_responsive(url)
    )
    return IntegrationSession(
        poll_url=f"http://{docker_ip}:8378",
        rootdir=path.join(str(pytestconfig.rootdir), "tests", "integration"),
    )


@pytest.fixture(scope="session")
def integration_local(pytestconfig):
    """Local non-docer based replacement for `integration` fixture"""
    return IntegrationSession(
        poll_url="http://localhost:8378",
        rootdir=path.join(str(pytestconfig.rootdir), "tests", "integration"),
    )


def is_responsive(url) -> bool:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True
    except ConnectionError:
        pass
    return False
