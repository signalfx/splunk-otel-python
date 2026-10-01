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
)


def test_disabled_file_skips_sdk_setup(tmp_path, caplog):
    config_file = tmp_path / "config.yaml"
    config_file.write_text('file_format: "1.0"\ndisabled: true\n')

    with caplog.at_level(logging.WARNING):
        config = _configure_declarative_sdk(str(config_file))

    assert config is None
    assert "disabled=true" in caplog.text


def test_invalid_file_fails_configuration(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text('file_format: "1.0"\ndisabled: [\n')

    with pytest.raises(ConfigurationError):
        _configure_declarative_sdk(str(config_file))


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
