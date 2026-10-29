#!/usr/bin/env python3
"""Validate one copied image payload across the supported application interpreters."""

import argparse
from pathlib import Path
import subprocess
import tempfile
import uuid


def docker(*args):
    subprocess.run(["docker", *args], check=True)


def configuration(protocol):
    exporter = "otlp_grpc" if protocol == "grpc" else "otlp_http"

    def endpoint(signal):
        return "http://127.0.0.1:4317" if protocol == "grpc" else f"http://127.0.0.1:4318/v1/{signal}"

    return f"""file_format: "1.0"
resource:
  attributes:
    - name: service.name
      value: image-test
tracer_provider:
  processors:
    - batch:
        exporter:
          {exporter}:
            endpoint: {endpoint("traces")}
meter_provider:
  readers:
    - periodic:
        exporter:
          {exporter}:
            endpoint: {endpoint("metrics")}
logger_provider:
  processors:
    - batch:
        exporter:
          {exporter}:
            endpoint: {endpoint("logs")}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--platform", action="append", choices=("linux/amd64", "linux/arm64"))
    parser.add_argument(
        "--python-version",
        action="append",
        choices=("3.10", "3.11", "3.12", "3.13", "3.14"),
    )
    parser.add_argument("--secureapp", action="store_true")
    args = parser.parse_args()
    test_app = Path(__file__).with_name("image_payload.py").resolve()
    for platform in args.platform or ("linux/amd64", "linux/arm64"):
        volume = f"splunk-python-compat-{uuid.uuid4().hex}"
        try:
            # Use the operator's cp command. All interpreters reuse this volume.
            docker(
                "run",
                "--rm",
                "--platform",
                platform,
                "-v",
                f"{volume}:/dest",
                args.image,
                "cp",
                "-r",
                "/autoinstrumentation/.",
                "/dest",
            )
            docker(
                "run",
                "--rm",
                "--platform",
                platform,
                "-v",
                f"{volume}:/dest:ro",
                args.image,
                "sh",
                "-ec",
                'size=$(du -sk /dest | cut -f1); echo "Payload: $size KiB"; test "$size" -lt 204800',
            )
            for version in args.python_version or (
                "3.10",
                "3.11",
                "3.12",
                "3.13",
                "3.14",
            ):
                for mode in ("environment", "declarative"):
                    for protocol in ("grpc", "http/protobuf"):
                        print(  # noqa: T201
                            f"Testing {args.image} {platform} Python {version}: {mode}, {protocol}",
                            flush=True,
                        )
                        with tempfile.TemporaryDirectory() as directory:
                            config = Path(directory, "config.yaml")
                            config.write_text(configuration(protocol))
                            customize = Path(directory, "sitecustomize.py")
                            customize.write_text("raise RuntimeError('application sitecustomize took precedence')\n")
                            env = [
                                "-e",
                                f"OTEL_CONFIG_FILE={'/test/config.yaml' if mode == 'declarative' else ''}",
                            ]
                            docker(
                                "run",
                                "--rm",
                                "--platform",
                                platform,
                                "--user",
                                "65534:65534",
                                "-v",
                                f"{volume}:/otel-auto-instrumentation-python:ro",
                                "-v",
                                f"{test_app}:/test/image_payload.py:ro",
                                "-v",
                                f"{config}:/test/config.yaml:ro",
                                "-v",
                                f"{customize}:/app/sitecustomize.py:ro",
                                "-e",
                                "PYTHONPATH=/otel-auto-instrumentation-python/opentelemetry/instrumentation/auto_instrumentation:/app:/otel-auto-instrumentation-python",
                                "-e",
                                "OTEL_SERVICE_NAME=image-test",
                                "-e",
                                "OTEL_TRACES_EXPORTER=otlp",
                                "-e",
                                "OTEL_METRICS_EXPORTER=otlp",
                                "-e",
                                "OTEL_LOGS_EXPORTER=otlp",
                                "-e",
                                f"OTEL_EXPORTER_OTLP_PROTOCOL={protocol}",
                                "-e",
                                f"OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:{4317 if protocol == 'grpc' else 4318}",
                                "-e",
                                "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=system_metrics,grpc_client,grpc_server",
                                "-e",
                                f"VERIFY_SECUREAPP={str(args.secureapp).lower()}",
                                *env,
                                f"python:{version}-slim-bookworm",
                                "python",
                                "/test/image_payload.py",
                            )
        finally:
            docker("volume", "rm", volume)


if __name__ == "__main__":
    main()
