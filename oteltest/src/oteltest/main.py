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
import venv
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from otelsink import GrpcSink, RequestHandler
from oteltest.common import OtelTest, Telemetry

VENV_DIR = "_oteltest_venv"


def main():
    run(sys.argv, VENV_DIR)


class AccumulatingHandler(RequestHandler):
    def __init__(self):
        self.telemetry = Telemetry()

    def handle_logs(self, request: ExportLogsServiceRequest, context):  # noqa: ARG002
        self.telemetry.add_log(MessageToDict(request))

    def handle_metrics(self, request: ExportMetricsServiceRequest, context):  # noqa: ARG002
        self.telemetry.add_metric(MessageToDict(request))

    def handle_trace(self, request: ExportTraceServiceRequest, context):  # noqa: ARG002
        self.telemetry.add_trace(MessageToDict(request))


def run(args, venv_dir):
    target_dir = args[1]
    sys.path.append(target_dir)
    scripts = ls_scripts(target_dir)
    for script in scripts:
        run_script(script, target_dir, venv_dir)


def ls_scripts(target_dir):
    out = []
    for script_name in glob.glob("*.py", root_dir=target_dir):
        print(script_name)
        out.append(script_name)
    return out


def run_script(script, target_dir, venv_dir):
    handler = AccumulatingHandler()
    sink = GrpcSink(handler)
    sink.start()
    print(f"Setting up script '{script}'")
    test_class = load_test_class_for_script(script)
    test_instance = test_class()
    venv.create(venv_dir, with_pip=True)
    print_run([to_venv_path(venv_dir, "pip"), "install", "./oteltest"])
    for req in test_instance.requirements():
        print(f"Installing requirement: '{req}'")
        print_run([to_venv_path(venv_dir, "pip"), "install", req])
    script_args = [to_venv_path(venv_dir, "python"), str(Path(target_dir) / script)]
    ws = test_instance.wrapper_script()
    if ws is not None:
        script_args.insert(0, to_venv_path(venv_dir, ws))
    print_run(script_args, test_instance.environment_variables())
    test_instance.validate(handler.telemetry)
    shutil.rmtree(venv_dir)


def to_venv_path(venv_dir, executable_name):
    return f"{venv_dir}/bin/{executable_name}"


def print_run(args, env_vars=None) -> None:
    print(f"Running {args}, env_vars: {env_vars}")
    result = subprocess.run(
        args,
        capture_output=True,
        env=env_vars,
    )
    print(f"Subprocess Result ('{args[0]}'):")
    print("--------------------------")
    print(f"Return Code: {result.returncode}")
    if result.stdout:
        stdout_output = result.stdout.decode('utf-8').strip()
        print("\nStandard Output:")
        print("----------------")
        print(stdout_output or "None")
    else:
        print("\nStandard Output: None")
    if result.stderr:
        stderr_output = result.stderr.decode('utf-8').strip()
        print("\nStandard Error:")
        print("---------------")
        print(stderr_output or "None")
    else:
        print("\nStandard Error: None")
    print("==========================\n")


def load_test_class_for_script(script_name):
    module_name = script_name[:-3]
    module = importlib.import_module(module_name)
    for attr_name in dir(module):
        value = getattr(module, attr_name)
        if is_test_class(value):
            return value
    return None


def is_test_class(value):
    return inspect.isclass(value) and issubclass(value, OtelTest) and value is not OtelTest


if __name__ == '__main__':
    main()
