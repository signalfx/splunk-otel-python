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

import glob
import importlib
import inspect
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from otelsink import GrpcSink, RequestHandler
from oteltest.common import OtelTest, Telemetry


def main():
    run(sys.argv)


def run(args):
    tempdir = tempfile.mkdtemp()
    print(f"using temp dir: {tempdir}")

    script_dir = args[1]
    sys.path.append(script_dir)
    scripts = ls_scripts(script_dir)
    for script in scripts:
        setup_script_environment(script, script_dir, tempdir)


def ls_scripts(target_dir):
    out = []
    for script_name in glob.glob("*.py", root_dir=target_dir):
        print(script_name)
        out.append(script_name)
    return out


def setup_script_environment(script, script_dir, tempdir):
    handler = AccumulatingHandler()
    sink = GrpcSink(handler)
    sink.start()

    module_name = script[:-3]
    test_class = load_test_class_for_script(module_name)
    test_instance: OtelTest = test_class()

    v = Venv(str(Path(tempdir) / module_name))
    v.create()

    pip_path = v.path_to_executable("pip")
    run_subprocess([pip_path, "install", "./oteltest"])

    for req in test_instance.requirements():
        print(f"- Will install requirement: '{req}'")
        run_subprocess([pip_path, "install", req])

    run_python_script(script, script_dir, test_instance, v)

    with open(str(Path(script_dir) / f"{module_name}.json"), "w") as file:
        file.write(handler.telemetry_to_json())

    test_instance.validate(handler.telemetry)


def run_python_script(script, script_dir, test_instance, v):
    python_script_cmd = [v.path_to_executable("python"), str(Path(script_dir) / script)]
    ws = test_instance.wrapper_script()
    if ws is not None:
        python_script_cmd.insert(0, v.path_to_executable(ws))
    run_subprocess(python_script_cmd, test_instance.environment_variables())


def run_subprocess(args, env_vars=None) -> None:
    print(f"- Subprocess: {args}")
    print(f"- Environment: {env_vars}")
    result = subprocess.run(
        args,
        capture_output=True,
        env=env_vars,
    )
    print(f"- Return Code: {result.returncode}")
    print("- Standard Output:")
    if result.stdout:
        print(result.stdout.decode('utf-8').strip())
    print("- Standard Error:")
    if result.stderr:
        print(result.stderr.decode('utf-8').strip())
    print("- End Subprocess -\n")


def load_test_class_for_script(module_name):
    module = importlib.import_module(module_name)
    for attr_name in dir(module):
        value = getattr(module, attr_name)
        if is_test_class(value):
            return value
    return None


def is_test_class(value):
    return inspect.isclass(value) and issubclass(value, OtelTest) and value is not OtelTest


class Venv:
    def __init__(self, venv_dir):
        self.venv_dir = venv_dir

    def create(self):
        venv.create(self.venv_dir, with_pip=True)

    def path_to_executable(self, executable_name: str):
        return f"{self.venv_dir}/bin/{executable_name}"

    def rm(self):
        shutil.rmtree(self.venv_dir)


class AccumulatingHandler(RequestHandler):
    def __init__(self):
        self.telemetry = Telemetry()

    def handle_logs(self, request: ExportLogsServiceRequest, context):  # noqa: ARG002
        self.telemetry.add_log(MessageToDict(request), get_context_headers(context))

    def handle_metrics(self, request: ExportMetricsServiceRequest, context):  # noqa: ARG002
        self.telemetry.add_metric(MessageToDict(request), get_context_headers(context))

    def handle_trace(self, request: ExportTraceServiceRequest, context):  # noqa: ARG002
        self.telemetry.add_trace(MessageToDict(request), get_context_headers(context))

    def telemetry_to_json(self):
        return self.telemetry.to_json()


def get_context_headers(context):
    return pbmetadata_to_dict(context.invocation_metadata())


def pbmetadata_to_dict(pbmetadata):
    out = {}
    for k, v in pbmetadata:
        out[k] = v
    return out


if __name__ == '__main__':
    main()
