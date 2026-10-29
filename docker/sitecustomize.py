"""Select the init-image dependencies for the application's interpreter."""

import os
from pathlib import Path
import sys
import sysconfig


def _initialize():
    startup_dir = Path(__file__).resolve().parent
    root = startup_dir.parents[2]
    packages = root / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if sys.implementation.name != "cpython" or sysconfig.get_config_var("Py_GIL_DISABLED") or not packages.is_dir():
        message = "The Splunk init image requires CPython 3.10-3.14 with the GIL enabled"
        raise RuntimeError(message)

    sys.path.insert(0, str(packages))

    from opentelemetry.instrumentation.auto_instrumentation import initialize

    # The upstream initializer removes its own directory from PYTHONPATH while
    # it runs. Remove this entry point too, so startup subprocesses cannot recurse.
    python_path = os.environ.get("PYTHONPATH")
    if python_path is not None:
        os.environ["PYTHONPATH"] = os.pathsep.join(
            path for path in python_path.split(os.pathsep) if Path(path).resolve() != startup_dir
        )
    try:
        initialize()
    finally:
        if python_path is not None:
            os.environ["PYTHONPATH"] = python_path


_initialize()
