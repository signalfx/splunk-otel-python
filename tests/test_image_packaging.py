import importlib.util
from pathlib import Path
import shutil


def test_shared_files_work_after_copying_the_payload(tmp_path):
    script = Path(__file__).resolve().parents[1] / "docker" / "deduplicate.py"
    spec = importlib.util.spec_from_file_location("deduplicate", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = tmp_path / "payload"
    for minor in ("3.10", "3.13", "3.14"):
        packages = payload / f"python{minor}"
        packages.mkdir(parents=True)
        (packages / "common.py").write_text("common source")
        (packages / "different.py").write_text(minor)
        (packages / f"native.cpython-{minor.replace('.', '')}.so").write_bytes(minor.encode())

    module.deduplicate(payload)
    destination = tmp_path / "copied"
    shutil.copytree(payload, destination, symlinks=True)

    for minor in ("3.10", "3.13", "3.14"):
        packages = destination / f"python{minor}"
        common = packages / "common.py"
        assert common.is_symlink() == (minor != "3.10")
        assert common.read_text() == "common source"
        assert (packages / "different.py").read_text() == minor
        native = packages / f"native.cpython-{minor.replace('.', '')}.so"
        assert not native.is_symlink()
        assert native.read_bytes() == minor.encode()
