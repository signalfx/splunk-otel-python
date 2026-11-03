import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="The release script runs in Linux CI.")
@pytest.mark.parametrize("available_on", [1, 10, None])
def test_publish_waits_for_pypi_package(tmp_path, available_on):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "docker").mkdir()
    version_dir = tmp_path / "src" / "splunk_otel"
    version_dir.mkdir(parents=True)
    version = "1.2.3"
    (version_dir / "__about__.py").write_text(f'__version__ = "{version}"\n')
    (tmp_path / "docker/requirements.txt").write_text(f"splunk-opentelemetry=={version}\n")
    (tmp_path / "docker/requirements-secureapp.txt").write_text("secureapp-python-agent==1.0\n")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "docker", "sleep", "artifact-ci"):
        command = fake_bin / name
        command.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "name = pathlib.Path(sys.argv[0]).name\n"
            "if name == 'curl':\n"
            "    path = pathlib.Path(os.environ['CURL_ATTEMPTS'])\n"
            "    attempt = int(path.read_text()) + 1 if path.exists() else 1\n"
            "    path.write_text(str(attempt))\n"
            "    sys.exit(0 if str(attempt) == os.environ['AVAILABLE_ON'] else 22)\n"
            "if name == 'docker':\n"
            "    with open(os.environ['DOCKER_CALLS'], 'a') as calls:\n"
            "        calls.write(' '.join(sys.argv[1:]) + '\\n')\n"
        )
        command.chmod(0o755)

    attempts = tmp_path / "attempts"
    docker_calls = tmp_path / "docker-calls"
    env = dict(
        os.environ,
        PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
        CI_COMMIT_TAG=f"v{version}",
        CI_COMMIT_REF_PROTECTED="true",
        SIGNING_SERVICE_ADDR="https://signing.invalid",
        QUAY_USERNAME="fake-user",
        QUAY_PASSWORD="fake-password",
        CURL_ATTEMPTS=str(attempts),
        AVAILABLE_ON=str(available_on),
        DOCKER_CALLS=str(docker_calls),
    )
    result = subprocess.run(
        ["bash", str(root / "docker/publish-docker-image.sh"), f"v{version}"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert int(attempts.read_text()) == (available_on or 10)
    if available_on is None:
        assert result.returncode == 1
        assert "was not found on PyPI after 10 attempts" in result.stdout
        assert not docker_calls.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert "was not found on PyPI" not in result.stdout
        assert sum("--push" in call for call in docker_calls.read_text().splitlines()) == 2
