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


import abc
from concurrent import futures

import grpc  # type: ignore
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2, logs_service_pb2_grpc  # type: ignore
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest  # type: ignore
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc  # type: ignore
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest  # type: ignore
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc  # type: ignore
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest  # type: ignore


class RequestHandler(abc.ABC):
    @abc.abstractmethod
    def handle_logs(self, request: ExportLogsServiceRequest, context):
        pass

    @abc.abstractmethod
    def handle_metrics(self, request: ExportMetricsServiceRequest, context):
        pass

    @abc.abstractmethod
    def handle_trace(self, request: ExportTraceServiceRequest, context):
        pass


class GrpcSink:
    def __init__(self, request_handler: RequestHandler):
        self._request_handler = request_handler
        self.svr = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
            TraceServiceServicer(request_handler.handle_trace), self.svr
        )
        metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(
            MetricsServiceServicer(request_handler.handle_metrics), self.svr
        )
        logs_service_pb2_grpc.add_LogsServiceServicer_to_server(
            LogsServiceServicer(request_handler.handle_logs), self.svr
        )
        self.svr.add_insecure_port("0.0.0.0:4317")

    def start(self):
        """Starts the server. Does not block."""
        self.svr.start()

    def wait_for_termination(self):
        """Blocks until the server stops"""
        self.svr.wait_for_termination()

    def stop(self):
        self.svr.stop(grace=None)


class LogsServiceServicer(logs_service_pb2_grpc.LogsServiceServicer):
    def __init__(self, handle_request):
        self.handle_request = handle_request

    def Export(self, request, context):  # noqa: N802
        self.handle_request(request, context)
        return logs_service_pb2.ExportLogsServiceResponse()


class TraceServiceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(self, handle_request):
        self.handle_request = handle_request

    def Export(self, request, context):  # noqa: N802
        self.handle_request(request, context)
        return trace_service_pb2.ExportTraceServiceResponse()


class MetricsServiceServicer(metrics_service_pb2_grpc.MetricsServiceServicer):
    def __init__(self, handle_request):
        self.handle_request = handle_request

    def Export(self, request, context):  # noqa: N802
        self.handle_request(request, context)
        return metrics_service_pb2.ExportMetricsServiceResponse()


class PrintHandler(RequestHandler):
    def handle_logs(self, request, context):  # noqa: ARG002
        print(f"log request: {request}")  # noqa: T201

    def handle_metrics(self, request, context):  # noqa: ARG002
        print(f"metrics request: {request}")  # noqa: T201

    def handle_trace(self, request: ExportTraceServiceRequest, context):  # noqa: ARG002
        print(f"trace request: {request}")  # noqa: T201


def run_print_server():
    sink = GrpcSink(PrintHandler())
    sink.start()
    sink.wait_for_termination()


if __name__ == "__main__":
    run_print_server()
