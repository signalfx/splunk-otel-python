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
import json
from typing import List, Mapping


class Telemetry:
    def __init__(self):
        self.logs = []
        self.metrics = []
        self.trace = []

    def add_log(self, log: dict):
        self.logs.append(log)

    def add_metric(self, metric: dict):
        self.metrics.append(metric)

    def add_trace(self, trace: dict):
        self.trace.append(trace)

    def get_traces(self):
        return self.trace

    def num_metrics(self) -> int:
        out = 0
        for metric in self.metrics:
            for rm in metric["resourceMetrics"]:
                for sm in rm["scopeMetrics"]:
                    out += len(sm["metrics"])
        return out

    def metric_names(self) -> set:
        out = set()
        for metric in self.metrics:
            for rm in metric["resourceMetrics"]:
                for sm in rm["scopeMetrics"]:
                    for m in sm["metrics"]:
                        out.add(m["name"])
        return out

    def num_spans(self) -> int:
        out = 0
        for tr in self.trace:
            for rs in tr["resourceSpans"]:
                for ss in rs["scopeSpans"]:
                    out += len(ss["spans"])
        return out

    def __str__(self):
        return self.to_json()

    def to_json(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        return {
            "logs": self.logs,
            "metrics": self.metrics,
            "trace": self.trace,
        }


def telemetry_from_json(json_data: str):
    pass


def trace_attribute_as_str_array(tr: dict, attr_name) -> [str]:
    out = []
    for rs in tr["resourceSpans"]:
        for attr in rs["resource"]["attributes"]:
            if attr["key"] == attr_name:
                out.append(attr["value"]["stringValue"])
    return out


class OtelTest(abc.ABC):
    @abc.abstractmethod
    def environment_variables(self) -> Mapping[str, str]:
        pass

    @abc.abstractmethod
    def requirements(self) -> List[str]:
        pass

    @abc.abstractmethod
    def wrapper_script(self) -> str:
        pass

    @abc.abstractmethod
    def validate(self, telemetry: Telemetry) -> None:
        pass
