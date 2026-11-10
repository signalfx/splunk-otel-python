import os
from pathlib import Path
import platform
import sys
import sysconfig


def main():
    if (
        sys.implementation.name != "cpython"
        or not (3, 10) <= sys.version_info[:2] <= (3, 14)
        or sys.platform != "linux"
        or platform.machine() != "x86_64"
        or sysconfig.get_config_var("Py_GIL_DISABLED")
    ):
        sys.exit(
            "The Splunk Python buildpack requires CPython 3.10-3.14 on Linux AMD64 with the GIL enabled."
        )

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    packages = Path(__file__).resolve().parent / "agent" / f"python{python_version}"
    if not packages.is_dir():
        sys.exit(f"Agent packages are missing for Python {python_version}: {packages}")

    # The instrument command replaces this process; the child needs the bundle too.
    python_path = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(packages) + (
        os.pathsep + python_path if python_path else ""
    )
    sys.path.insert(0, str(packages))

    from opentelemetry.instrumentation.auto_instrumentation import run

    run()


if __name__ == "__main__":
    main()
