from pathlib import Path

from tools.generate_metadata import (
    build_instrumentation,
    dependency_stability,
    dump_yaml,
    generate_metadata,
    load_toml_bytes,
    parse_requirement,
)


def write_project(root: Path) -> None:
    package_dir = root / "src" / "splunk_otel"
    package_dir.mkdir(parents=True)
    (package_dir / "__about__.py").write_text('__version__ = "9.8.7"\n')
    (root / "pyproject.toml").write_text(
        """
[project]
dependencies = [
  "opentelemetry-api==1.2.3",
  "opentelemetry-sdk==1.2.3",
  "opentelemetry-instrumentation==0.4b5",
  "opentelemetry-instrumentation-system-metrics==0.4b5",
  "opentelemetry-opamp-client==0.1b0",
  "wrapt>=1.0.0,<2.0.0",
]
"""
    )


def write_contrib(root: Path) -> None:
    instrumentation = root / "instrumentation" / "opentelemetry-instrumentation-example"
    instrumentation.mkdir(parents=True)
    (instrumentation / "pyproject.toml").write_text(
        """
[project]
name = "opentelemetry-instrumentation-example"
description = "Example instrumentation"
dependencies = ["opentelemetry-instrumentation == 0.4b5"]

[project.optional-dependencies]
instruments = ["example-lib >= 1.0, < 2.0"]

[project.entry-points.opentelemetry_instrumentor]
example = "opentelemetry.instrumentation.example:ExampleInstrumentor"
"""
    )


def test_parse_requirement_normalizes_exact_pins() -> None:
    assert parse_requirement("opentelemetry-api==1.2.3") == ("opentelemetry-api", "1.2.3")
    assert parse_requirement("wrapt>=1.0.0,<2.0.0") == ("wrapt", ">=1.0.0,<2.0.0")


def test_dependency_stability_uses_prerelease_versions() -> None:
    assert dependency_stability("1.41.0") == "stable"
    assert dependency_stability(">=6.33.5") == "stable"
    assert dependency_stability("0.62b0") == "experimental"
    assert dependency_stability("1.42.0rc1") == "experimental"
    assert dependency_stability("1.42.0.dev") == "experimental"


def test_build_instrumentation_from_pyproject() -> None:
    pyproject = load_toml_bytes(
        b"""
[project]
name = "opentelemetry-instrumentation-flask"
description = "Flask instrumentation"

[project.optional-dependencies]
instruments = ["flask >= 1.0"]

[project.entry-points.opentelemetry_instrumentor]
flask = "opentelemetry.instrumentation.flask:FlaskInstrumentor"
"""
    )

    instrumentation = build_instrumentation(
        "instrumentation/opentelemetry-instrumentation-flask/pyproject.toml",
        pyproject,
    )

    assert instrumentation is not None
    assert instrumentation["keys"] == ["flask"]
    assert instrumentation["instrumented_components"] == [
        {
            "name": "flask",
            "supported_versions": "flask >= 1.0",
        }
    ]
    assert instrumentation["support"] == "community"
    assert instrumentation["stability"] == "experimental"


def test_generate_metadata_shape(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    contrib_root = tmp_path / "contrib"
    project_root.mkdir()
    contrib_root.mkdir()
    write_project(project_root)
    write_contrib(contrib_root)

    metadata = generate_metadata(project_root, contrib_root, allow_download=False)

    assert metadata["component"] == "Splunk Distribution of OpenTelemetry Python"
    assert metadata["version"] == "9.8.7"
    assert [dependency["name"] for dependency in metadata["dependencies"][:2]] == [
        "OpenTelemetry Python",
        "OpenTelemetry Python Contrib",
    ]
    dependencies_by_name = {dependency["name"]: dependency for dependency in metadata["dependencies"]}
    assert dependencies_by_name["OpenTelemetry Python"]["stability"] == "stable"
    assert dependencies_by_name["OpenTelemetry Python Contrib"]["stability"] == "experimental"
    assert dependencies_by_name["opentelemetry-instrumentation-system-metrics"]["stability"] == "experimental"
    assert dependencies_by_name["wrapt"]["stability"] == "stable"
    assert "property" in metadata["settings"][0]
    assert "metrics" in metadata
    assert metadata["resource_detectors"]
    assert "dependencies" not in metadata["resource_detectors"][0]
    assert any(item["keys"] == ["example"] for item in metadata["instrumentations"])
    assert not any(item["keys"] == ["splunk-profiling"] for item in metadata["instrumentations"])
    assert not any(item["keys"] == ["splunk-trace-response-header"] for item in metadata["instrumentations"])

    yaml_text = dump_yaml(metadata)
    assert "component: 'Splunk Distribution of OpenTelemetry Python'" in yaml_text
    assert "resource_detectors:" in yaml_text
