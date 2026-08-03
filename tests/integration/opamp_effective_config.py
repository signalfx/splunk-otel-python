import time

from lib import project_path

_SERVICE_NAME = "opamp-effective-config-test"


if __name__ == "__main__":
    time.sleep(4)


class OpAMPEffectiveConfigOtelTest:
    def __init__(self):
        self.effective_config_seen = False

    def requirements(self):
        return (project_path(),)

    def environment_variables(self):
        return {
            "NO_PROXY": "127.0.0.1,localhost",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "system_metrics",
            "OTEL_SERVICE_NAME": _SERVICE_NAME,
            "SPLUNK_OPAMP_ENABLED": "true",
            "SPLUNK_OPAMP_ENDPOINT": "http://127.0.0.1:4320/v1/opamp",
            "SPLUNK_OPAMP_POLLING_INTERVAL": "60000",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "1234",
            "SPLUNK_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL": "17",
        }

    def wrapper_command(self):
        return "opentelemetry-instrument"

    def on_start(self):
        return None

    def on_opamp(
        self,
        effective_config,
        remote_config_status,
        remote_config_error,
    ):
        self.effective_config_seen = True
        assert effective_config == {
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://127.0.0.1:4318/v1/traces",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://127.0.0.1:4318/v1/metrics",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://127.0.0.1:4318/v1/logs",
            "SPLUNK_PROFILER_ENABLED": "false",
            "SPLUNK_PROFILER_MEMORY_ENABLED": "false",
            "SPLUNK_SNAPSHOT_PROFILER_ENABLED": "false",
            "SPLUNK_SNAPSHOT_PROFILER_SAMPLING_INTERVAL": "17",
            "SPLUNK_PROFILER_CALL_STACK_INTERVAL": "1234",
            "OTEL_CONFIG_FILE": "null",
            "OTEL_EXPERIMENTAL_CONFIG_FILE": "null",
        }
        assert remote_config_status is None
        assert remote_config_error is None

    def on_stop(self, _telemetry, stdout: str, stderr: str, returncode: int):
        assert returncode == 0, f"{stdout}\n{stderr}"
        assert self.effective_config_seen

    def is_http(self):
        return True
