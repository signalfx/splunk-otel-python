import os
from pathlib import Path
import platform
import sys
import sysconfig


def main():
    if (
        sys.implementation.name != "cpython"
        or sys.version_info[:2] != (3, 12)
        or sys.platform != "linux"
        or platform.machine() != "x86_64"
        or sysconfig.get_config_var("Py_GIL_DISABLED")
    ):
        sys.exit(
            "The Splunk Python buildpack requires CPython 3.12 on Linux AMD64 with the GIL enabled."
        )

    packages = Path(__file__).resolve().parent / "agent" / "packages"
    if not packages.is_dir():
        sys.exit("The Splunk Python buildpack agent packages are missing.")

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
