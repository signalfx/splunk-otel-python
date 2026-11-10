from importlib.metadata import version
from pathlib import Path

from app import app
import splunk_secureapp_opentelemetry_extension


packages = Path("/runtime-deps/0/agent/packages")
assert Path(splunk_secureapp_opentelemetry_extension.__file__).is_relative_to(packages)
assert version("secureapp-python-agent")

response = app.test_client().get("/")
assert response.status_code == 200
assert response.json == {"message": "Hello from Cloud Foundry"}
