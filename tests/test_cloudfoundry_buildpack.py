import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


BUILDPACK = Path(__file__).resolve().parents[1] / "deployments/cloudfoundry/buildpack"
pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Cloud Foundry scripts require Linux"
)


@pytest.fixture
def buildpack(tmp_path):
    directory = tmp_path / "buildpack"
    shutil.copytree(BUILDPACK, directory, ignore=shutil.ignore_patterns("*.zip"))
    agent = directory / "agent"
    (agent / "packages").mkdir(parents=True)
    (agent / "VERSION").write_text("2.13.3\n")
    return directory


def _supply(buildpack, tmp_path, **environment):
    directories = [
        tmp_path / name for name in ("application", "cache", "staged dependencies")
    ]
    for directory in directories:
        directory.mkdir(exist_ok=True)
    return subprocess.run(
        [
            "bash",
            str(buildpack / "bin/supply"),
            *(str(path) for path in directories),
            "0",
        ],
        env={
            **os.environ,
            "CF_STACK": "cflinuxfs4",
            "SPLUNK_OTEL_PYTHON_VERSION": "2.13.3",
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_supply_and_launch_after_dependencies_move(buildpack, tmp_path):
    result = _supply(buildpack, tmp_path)
    assert result.returncode == 0, result.stderr
    assert not list((tmp_path / "application").iterdir())
    assert not list((tmp_path / "cache").iterdir())
    staged = tmp_path / "staged dependencies"
    assert [path.name for path in staged.iterdir()] == ["0"]
    assert (staged / "0/agent/VERSION").read_text() == "2.13.3\n"

    runtime = tmp_path / "runtime dependencies"
    shutil.move(staged, runtime)
    fake_python = tmp_path / "python"
    fake_python.write_text(
        f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n"
    )
    fake_python.chmod(0o755)
    result = subprocess.run(
        [str(runtime / "0/bin/splunk-otel-python"), "gunicorn", "argument with spaces"],
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [
        str(runtime / "0/launch.py"),
        "gunicorn",
        "argument with spaces",
    ]


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"CF_STACK": "cflinuxfs3"}, "requires cflinuxfs4"),
        (
            {"SPLUNK_OTEL_PYTHON_VERSION": "0.0.0"},
            "bundles splunk-opentelemetry 2.13.3",
        ),
    ],
)
def test_supply_rejects_incompatible_configuration(
    buildpack, tmp_path, environment, message
):
    result = _supply(buildpack, tmp_path, **environment)
    assert result.returncode == 1
    assert message in result.stderr
    assert not list((tmp_path / "staged dependencies").iterdir())


def test_supply_rejects_unbuilt_source(tmp_path):
    result = _supply(BUILDPACK, tmp_path)
    assert result.returncode == 1
    assert "Agent payload missing" in result.stderr


@pytest.mark.parametrize("script", ["detect", "finalize", "supply"])
def test_buildpack_rejects_automatic_detection_final_position_and_missing_arguments(
    script,
):
    result = subprocess.run(
        ["bash", str(BUILDPACK / "bin" / script)], capture_output=True, check=False
    )
    assert result.returncode == 1


def test_launcher_rejects_unsupported_interpreter():
    if sys.platform == "linux" and sys.version_info[:2] == (3, 12):
        pytest.skip("This interpreter can run the buildpack")
    result = subprocess.run(
        [sys.executable, str(BUILDPACK / "launch.py"), "python", "-V"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "requires CPython 3.12 on Linux AMD64" in result.stderr
