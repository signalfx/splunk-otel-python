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

import logging
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest
from opentelemetry.configuration import ConfigurationError
from opentelemetry.configuration.models import (
    AttributeNameValue,
    OpenTelemetryConfiguration,
    Resource as ResourceConfig,
)

from splunk_otel.configurator import (
    _configure_declarative_sdk,
    _create_declarative_resource,
    _declarative_server_timing_enabled,
    SplunkConfigurator,
)


def test_disabled_file_skips_sdk_setup(tmp_path, caplog):
    config_file = tmp_path / "config.yaml"
    config_file.write_text('file_format: "1.0"\ndisabled: true\n')

    with caplog.at_level(logging.WARNING):
        config = _configure_declarative_sdk(str(config_file))

    assert config is None
    assert "disabled=true" in caplog.text


@pytest.mark.parametrize("enable_profiling", [False, True])
def test_environment_configuration_does_not_import_file_configuration(enable_profiling):
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OTEL_", "SPLUNK_"))}
    env.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
        OTEL_SERVICE_NAME="environment-test",
        OTEL_TRACES_EXPORTER="none",
        OTEL_METRICS_EXPORTER="none",
        OTEL_LOGS_EXPORTER="none",
        OTEL_PYTHON_DISABLED_INSTRUMENTATIONS="system_metrics",
        SPLUNK_PROFILER_ENABLED=str(enable_profiling).lower(),
        SPLUNK_SNAPSHOT_PROFILER_ENABLED=str(enable_profiling).lower(),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "from importlib.abc import MetaPathFinder\n"
                "class BlockFileConfigurationImports(MetaPathFinder):\n"
                "    def find_spec(self, fullname, path, target=None):\n"
                "        if fullname.startswith(('opentelemetry.configuration', 'jsonschema', 'rpds')):\n"
                "            raise ImportError(fullname)\n"
                "sys.meta_path.insert(0, BlockFileConfigurationImports())\n"
                "from splunk_otel.configurator import SplunkConfigurator\n"
                "SplunkConfigurator().configure()\n"
                "assert 'opentelemetry.configuration' not in sys.modules\n"
                "assert 'jsonschema' not in sys.modules\n"
                "assert 'rpds' not in sys.modules\n"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_invalid_file_fails_configuration(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text('file_format: "1.0"\ndisabled: [\n')

    with pytest.raises(ConfigurationError):
        _configure_declarative_sdk(str(config_file))


@pytest.mark.parametrize("existing_provider", ["none", "sdk", "noop"])
def test_callgraphs_uses_the_registered_tracer_provider(tmp_path, existing_provider):
    config_file = tmp_path / "callgraphs.yaml"
    config_file.write_text(
        'file_format: "1.0"\n'
        "resource:\n"
        "  attributes:\n"
        "    - name: service.name\n"
        "      value: yaml-service\n"
        "distribution:\n"
        "  splunk:\n"
        "    profiling:\n"
        "      callgraphs: {}\n"
    )
    script = dedent("""
        import sys
        from unittest.mock import patch
        from opentelemetry import trace
        from opentelemetry.configuration import ConfigurationError
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON
        from splunk_otel.configurator import _configure_declarative_sdk

        existing_provider = sys.argv[2]
        original = None
        if existing_provider == "sdk":
            original = TracerProvider(resource=Resource({"service.name": "existing-service"}), sampler=ALWAYS_ON)
        elif existing_provider == "noop":
            original = trace.NoOpTracerProvider()
        if original is not None:
            trace.set_tracer_provider(original)

        if existing_provider == "noop":
            with patch(
                "splunk_otel._declarative_profiling.create_tracer_provider",
                side_effect=AssertionError("Call graphs created a provider despite an incompatible global provider"),
            ):
                try:
                    _configure_declarative_sdk(sys.argv[1])
                except ConfigurationError as error:
                    assert "distribution.splunk.profiling.callgraphs" in str(error)
                    assert "already configured" in str(error)
                else:
                    raise AssertionError("Call graphs accepted an incompatible tracer provider")
            assert trace.get_tracer_provider() is original
        else:
            _configure_declarative_sdk(sys.argv[1])
            provider = trace.get_tracer_provider()
            assert isinstance(provider, TracerProvider)
            if original is not None:
                assert provider is original
                assert provider.resource.attributes["service.name"] == "existing-service"
            else:
                assert provider.resource.attributes["service.name"] == "yaml-service"
            with trace.get_tracer("test").start_as_current_span("request") as span:
                assert span.is_recording()
            provider.shutdown()
    """)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OTEL_", "SPLUNK_"))}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["OTEL_TRACES_SAMPLER"] = "always_off"
    result = subprocess.run(
        [sys.executable, "-c", script, str(config_file), existing_provider],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_declarative_resource_adds_distro_metadata_and_service_fallback(caplog):
    with caplog.at_level(logging.WARNING):
        resource = _create_declarative_resource(None)

    assert resource.attributes["service.name"] == "unnamed-python-service"
    assert resource.attributes["telemetry.distro.name"] == "splunk-opentelemetry"
    assert resource.attributes["telemetry.distro.version"]
    assert "service.name" in caplog.text


def test_declarative_resource_preserves_explicit_service_name(caplog):
    config = ResourceConfig(attributes=[AttributeNameValue(name="service.name", value="configured-service")])

    with caplog.at_level(logging.WARNING):
        resource = _create_declarative_resource(config)

    assert resource.attributes["service.name"] == "configured-service"
    assert not caplog.text


def test_declarative_server_timing_is_enabled_by_default():
    config = OpenTelemetryConfiguration(file_format="1.0")

    assert _declarative_server_timing_enabled(config)


def test_declarative_server_timing_reads_splunk_http_configuration():
    config = OpenTelemetryConfiguration(
        file_format="1.0",
        distribution={
            "splunk": {
                "instrumentations": {
                    "http": {"trace_response_header_enabled": False},
                },
            },
        },
    )

    assert not _declarative_server_timing_enabled(config)


@pytest.mark.parametrize("use_config_file", [False, True])
def test_configurator_activates_postgresql_only_without_config_file(monkeypatch, use_config_file):
    enable_calls = []
    monkeypatch.setenv("SPLUNK_DB_TRACE_CONTEXT_PROPAGATION_ENABLED", "true")
    if use_config_file:
        monkeypatch.setenv("OTEL_CONFIG_FILE", "config.yaml")
    else:
        monkeypatch.delenv("OTEL_CONFIG_FILE", raising=False)
    monkeypatch.setattr(
        "opentelemetry.sdk._configuration._OTelSDKConfigurator._configure",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "splunk_otel.configurator._configure_declarative_sdk",
        lambda *_a, **_k: OpenTelemetryConfiguration(file_format="1.0"),
    )
    monkeypatch.setattr("splunk_otel.configurator.configure_logging_instrumentation", lambda _env: None)
    monkeypatch.setattr("splunk_otel.configurator._start_profiling_if_enabled", lambda: None)
    monkeypatch.setattr("splunk_otel.configurator._configure_callgraphs_if_enabled", lambda: None)
    monkeypatch.setattr(
        "splunk_otel.runtime.enable_postgresql_trace_context_propagation",
        lambda: enable_calls.append(True),
    )

    SplunkConfigurator().configure()

    assert enable_calls == ([] if use_config_file else [True])
