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

import http.client
import unittest
from unittest import mock

from opentelemetry import trace as trace_api
from opentelemetry.exporter.jaeger import thrift as jaeger_exporter
from opentelemetry.sdk import trace

from splunk_otel.options import Options
from splunk_otel.tracing import _new_jaeger_exporter


class TestJaegerExporter(unittest.TestCase):
    def setUp(self):
        self.endpoint = "http://localhost:9080/v1/trace"
        self.service_name = "test-srv"
        context = trace_api.SpanContext(
            trace_id=0x000000000000000000000000DEADBEEF,
            span_id=0x00000000DEADBEF0,
            is_remote=False,
        )

        self._test_span = trace._Span("test_span", context=context)
        self._test_span.start()
        self._test_span.end()

        self.connection_patcher = mock.patch("http.client.HTTPConnection")
        self.connection_mock = self.connection_patcher.start()
        conn = self.connection_mock.return_value
        response = http.client.HTTPResponse(mock.Mock())
        response.status = 200
        conn.getresponse.return_value = response

    def tearDown(self):
        self.connection_patcher.stop()

    def test_exporter_uses_collector_not_udp_agent(self):
        exporter = _new_jaeger_exporter(
            Options(
                endpoint=self.endpoint,
                resource_attributes={"service.name": self.service_name},
            )
        )
        agent_client_mock = mock.Mock(spec=jaeger_exporter.AgentClientUDP)
        exporter._agent_client = agent_client_mock  # pylint:disable=protected-access
        collector_mock = mock.Mock(spec=jaeger_exporter.Collector)
        exporter._collector = collector_mock  # pylint:disable=protected-access

        exporter.export((self._test_span,))
        self.assertEqual(agent_client_mock.emit.call_count, 0)
        self.assertEqual(collector_mock.submit.call_count, 1)

    def test_http_export(self):
        exporter = _new_jaeger_exporter(
            Options(
                endpoint=self.endpoint,
                resource_attributes={"service.name": self.service_name},
            )
        )
        exporter.export((self._test_span,))

        conn = self.connection_mock.return_value
        conn.putrequest.assert_called_once_with("POST", "/v1/trace")
        conn.putheader.assert_any_call("User-Agent", "Python/THttpClient (pytest)")
        conn.putheader.assert_any_call("Content-Type", "application/x-thrift")

    def test_http_export_with_authentication(
        self,
    ):
        access_token = "test-access-token"
        exporter = _new_jaeger_exporter(
            Options(
                endpoint=self.endpoint,
                access_token=access_token,
                resource_attributes={"service.name": self.service_name},
            )
        )
        exporter.export((self._test_span,))

        conn = self.connection_mock.return_value
        conn.putrequest.assert_called_once_with("POST", "/v1/trace")
        conn.putheader.assert_any_call(
            "Authorization", "Basic YXV0aDp0ZXN0LWFjY2Vzcy10b2tlbg=="
        )
        conn.putheader.assert_any_call("User-Agent", "Python/THttpClient (pytest)")
        conn.putheader.assert_any_call("Content-Type", "application/x-thrift")
