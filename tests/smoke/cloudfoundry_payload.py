import importlib
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
import sys

from app import app
import splunk_secureapp_opentelemetry_extension


packages = Path(f"/tmp/runtime-deps/0/agent/python{sys.version_info.major}.{sys.version_info.minor}")
assert Path(splunk_secureapp_opentelemetry_extension.__file__).is_relative_to(packages)
assert version("secureapp-python-agent")

native_modules = (
    "rpds.rpds",
    "grpc._cython.cygrpc",
    "google._upb._message",
    "wrapt._wrappers",
    "charset_normalizer.cd",
    "charset_normalizer.md",
    "yaml._yaml",
    "psutil._psutil_linux",
)
if find_spec("uuid_utils") is not None:
    native_modules += ("uuid_utils._uuid_utils",)
for name in native_modules:
    module = importlib.import_module(name)
    assert Path(module.__file__).is_relative_to(packages), module.__file__

response = app.test_client().get("/")
assert response.status_code == 200
assert response.json == {"message": "Hello from Cloud Foundry"}
