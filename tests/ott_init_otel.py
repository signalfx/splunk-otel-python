from collections.abc import Mapping, Sequence
from typing import Optional

from oteltest.telemetry import count_spans
from ott_lib import project_path, trace_loop

NUM_SPANS = 12

if __name__ == "__main__":
    from splunk_otel import init_splunk_otel

    init_splunk_otel()
    trace_loop(NUM_SPANS)


class ConfigureOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return [project_path(), "oteltest"]

    def wrapper_command(self) -> str:
        return ""

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        assert count_spans(tel) == NUM_SPANS

    def is_http(self) -> bool:
        return False
