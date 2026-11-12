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

import atexit
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Empty, Queue
from threading import Event, Thread
from uuid import UUID

import pytest
from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.proto import opamp_pb2

from splunk_otel.env import Env
from splunk_otel.opamp import _build_client, _start_agent, build_effective_config_report


@dataclass(frozen=True)
class _ReceivedRequest:
    message: opamp_pb2.AgentToServer
    instance_uid_header: str | None
    body: bytes


class _OpAMPServer:
    def __init__(self):
        self._requests = Queue()
        self._responses = Queue()
        self._finishing = Event()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                server._requests.put(
                    _ReceivedRequest(
                        opamp_pb2.AgentToServer.FromString(body),
                        self.headers.get("OpAMP-Instance-UID"),
                        body,
                    )
                )
                status, response = 200, opamp_pb2.ServerToAgent()
                while not server._finishing.is_set():
                    try:
                        status, response = server._responses.get(timeout=0.05)
                        break
                    except Empty:
                        continue
                response_body = response.SerializeToString()
                self.send_response(status)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, *_args):
                pass

        self._http_server = HTTPServer(("127.0.0.1", 0), Handler)
        self.endpoint = f"http://127.0.0.1:{self._http_server.server_port}/v1/opamp"
        self._thread = Thread(target=partial(self._http_server.serve_forever, poll_interval=0.01), daemon=True)

    def start(self):
        self._thread.start()

    def next_request(self):
        try:
            return self._requests.get(timeout=5)
        except Empty:
            pytest.fail("No OpAMP HTTP request received within 5 seconds")

    def respond(self, message=None, *, status=200):
        self._responses.put((status, message if message is not None else opamp_pb2.ServerToAgent()))

    def finish_requests(self):
        # Let pending requests and the disconnect complete even when a test fails.
        self._finishing.set()

    def close(self):
        self.finish_requests()
        self._http_server.shutdown()
        self._http_server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def opamp_server(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    server = _OpAMPServer()
    server.start()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def opamp_agent_factory(opamp_server):
    agents = []

    def start_agent(*, polling_interval_ms=60000):
        client = _build_client(opamp_server.endpoint, {"service.name": "opamp-integration-test"})
        agent = _start_agent(
            polling_interval_ms,
            build_effective_config_report(Env({})),
            client,
            # Use public constructor options to test retry exhaustion without long backoffs.
            agent_factory=partial(OpAMPAgent, max_retries=1, initial_backoff=0),
        )
        agents.append(agent)
        return agent, client

    try:
        yield start_agent
    finally:
        opamp_server.finish_requests()
        for agent in agents:
            try:
                agent.stop(timeout=5)
            finally:
                atexit.unregister(agent.stop)


def test_initial_state_retries_beyond_retry_limit_before_sending_heartbeats(opamp_server, opamp_agent_factory):
    opamp_agent_factory(polling_interval_ms=10)
    initial = opamp_server.next_request()
    assert initial.message.HasField("agent_description")
    config_file = initial.message.effective_config.config_map.config_map["environment"]
    assert config_file.content_type == "text/plain; format=properties; vendor=splunk; v=1.0.0"
    assert config_file.body.decode() == build_effective_config_report(Env({}))

    # Exceed max_retries=1: every failed attempt must still send the initial state.
    for _ in range(3):
        opamp_server.respond(status=503)
        retry = opamp_server.next_request()
        assert retry.body == initial.body

    opamp_server.respond()
    heartbeat = opamp_server.next_request()
    assert not heartbeat.message.HasField("agent_description")
    assert not heartbeat.message.HasField("effective_config")
    assert heartbeat.message.sequence_num == initial.message.sequence_num + 1


def test_queued_messages_use_server_assigned_instance_id_in_body_and_header(opamp_server, opamp_agent_factory):
    agent, client = opamp_agent_factory()
    initial = opamp_server.next_request()
    assigned_uid = UUID("12345678-1234-4234-8234-123456789abc")
    assert initial.message.instance_uid != assigned_uid.bytes
    assert initial.instance_uid_header == str(UUID(bytes=initial.message.instance_uid))

    agent.send(client.build_heartbeat_message())
    agent.send(client.build_full_state_message())
    opamp_server.respond(
        opamp_pb2.ServerToAgent(agent_identification=opamp_pb2.AgentIdentification(new_instance_uid=assigned_uid.bytes))
    )

    for sequence_num in (1, 2):
        request = opamp_server.next_request()
        assert request.message.instance_uid == assigned_uid.bytes
        assert request.instance_uid_header == str(assigned_uid)
        assert request.message.sequence_num == sequence_num
        opamp_server.respond()


def test_retries_reuse_sequence_number_and_queued_messages_get_consecutive_numbers(opamp_server, opamp_agent_factory):
    agent, client = opamp_agent_factory()
    initial = opamp_server.next_request()
    assert initial.message.sequence_num == 0

    for _ in range(3):
        agent.send(client.build_heartbeat_message())
    opamp_server.respond()
    first = opamp_server.next_request()
    assert first.message.sequence_num == 1

    opamp_server.respond(status=503)
    retry = opamp_server.next_request()
    assert retry.body == first.body
    assert retry.instance_uid_header == first.instance_uid_header
    opamp_server.respond()

    for sequence_num in (2, 3):
        request = opamp_server.next_request()
        assert request.message.sequence_num == sequence_num
        opamp_server.respond()
