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
import http.client
import time

from oteltest import OtelTest, Telemetry

HOST = "0.0.0.0"
PORT = 9764

if __name__ == "__main__":
    import json

    import falcon
    from wsgiref import simple_server

    class HelloWorldResource(object):
        def on_get(self, req, resp):
            resp.status = falcon.HTTP_200
            resp.body = json.dumps({"hello": "world"})

    class ErrorResource(object):
        def on_get(self, req, resp):
            raise NameError("")

    app = falcon.API()

    app.add_route("/hello", HelloWorldResource())
    app.add_route("/error", ErrorResource())

    httpd = simple_server.make_server(HOST, PORT, app)
    httpd.serve_forever()


class MyOtelTest(OtelTest):
    def requirements(self):
        return (
            "falcon==2.0.0",
            "splunk-opentelemetry[all]==1.19.1",
            "opentelemetry-instrumentation-falcon==0.45b0",
        )

    def environment_variables(self):
        return {
            "OTEL_SERVICE_NAME": "my-service",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        time.sleep(10)

        conn = http.client.HTTPConnection(HOST, PORT)

        conn.request("GET", "/hello")
        print("hello response:", conn.getresponse().read().decode())

        conn.request("GET", "/error")
        print("error response:", conn.getresponse().read().decode())

        conn.close()

        return 60

    def on_stop(
        self,
        telemetry: Telemetry,
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> None:
        pass
