# Splunk OpenTelemetry Python buildpack for Cloud Foundry

This experimental classic Cloud Foundry buildpack supplies Splunk OpenTelemetry
Python, the Cisco SecureApp Python agent, and instrumentation packages before
the Cloud Foundry Python buildpack sets up the application. It follows the [Splunk Java add-on buildpack][java]
for explicit selection, ZIP packaging, and separation from the language runtime.

The draft targets **CPython 3.12, Linux AMD64, and cflinuxfs4**. Cloud Foundry
staging and deployment validation are pending. A successful local smoke test
does not establish PCF compatibility.

## How it works

1. `build.sh` installs the distribution's `secureapp` extra with the versions in
   [docker/requirements-secureapp.txt][secureapp-requirements] and
   [docker/requirements.txt][requirements]
   into a Linux package bundle and includes that bundle in a buildpack ZIP.
   Binary dependencies use manylinux2014 AMD64 wheels.
2. Cloud Foundry runs `bin/supply`, which copies the bundled agent and launch
   command into this buildpack's `deps/<index>` directory. It does not need
   Python during staging and does not change application files.
3. The final Python buildpack supplies the interpreter, installs the application
   requirements, and adds buildpack dependency `bin` directories to `PATH`.
4. The application starts with `splunk-otel-python <command>`. The launcher
   selects the bundled packages and calls the standard
   `opentelemetry-instrument` entry point before executing the application.

The launch command derives paths from its installed location, so it can run
when Cloud Foundry moves the dependency directory. It sets `PYTHONPATH` at
launch, after the Python buildpack has set its environment. Restarts do not run
pip or download agent packages.

The `detect` script returns 1, as Java's does, so select the buildpack explicitly.
The `finalize` script reports an error if this buildpack is placed last.

## Build and install

Building requires Docker with Linux AMD64 support and the `zip` command.
The build downloads Python packages. Run from the repository root:

```sh
./deployments/cloudfoundry/buildpack/build.sh
cf create-buildpack splunk_otel_python_buildpack \
  deployments/cloudfoundry/buildpack/splunk_otel_python_buildpack-linux.zip 99
```

The build script also accepts an output ZIP path as its first argument and an
agent wheel as its second argument. To package the current checkout:

```sh
python3 -m pip wheel --no-deps --wheel-dir dist .
./deployments/cloudfoundry/buildpack/build.sh \
  /tmp/splunk_otel_python_buildpack-linux.zip dist/splunk_opentelemetry-*.whl
```

The GitHub Actions buildpack job uses this wheel option, runs the Linux smoke
test, and uploads the tested ZIP as a workflow artifact. It does not publish a
release. Other dependencies still come from `docker/requirements.txt` and
`docker/requirements-secureapp.txt`. SecureApp is included in every buildpack;
the wheel option also requests the `secureapp` extra.

For stable release tags in the GitLab mirror, `build-job` packages the release
wheel into a buildpack and runs the same smoke test. The following jobs sign the
ZIP, calculate checksums, and sign the checksum file. The final
`checksum-signing-job` artifact includes the ZIP and its signature under
`buildpack-dist/`, alongside the Python package artifacts under `dist/`.
See [the release instructions](../../RELEASING.md#stable-release-process) for
uploading those files as GitHub Release assets.

Use the packaged ZIP rather than pointing `cf push` at this source directory:
source files do not include the agent bundle. A platform administrator may need
to install the ZIP.

## Deploy the example

The [example](example) contains a Flask route, application requirements,
`runtime.txt`, and a Cloud Foundry manifest. The application requirements do not
include the agent; the buildpack supplies it.

The manifest selects these buildpacks in order:

```yaml
buildpacks:
  - splunk_otel_python_buildpack
  - python_buildpack
command: splunk-otel-python gunicorn --bind 0.0.0.0:$PORT app:app
```

Your platform must provide a Python buildpack with CPython 3.12 support. Adjust
its installed buildpack name if it differs from `python_buildpack`.

Configure an export destination before starting the application. For a reachable
Collector, run:

```sh
cd deployments/cloudfoundry/example
cf push --no-start
cf set-env splunk-otel-python-example OTEL_EXPORTER_OTLP_ENDPOINT https://collector.example.com:4317
cf start splunk-otel-python-example
```

Replace the example endpoint with your Collector. Alternatively, set
`SPLUNK_REALM` and `SPLUNK_ACCESS_TOKEN` for direct export, following the
[distribution setup instructions][setup]. The buildpack does not deploy a
Collector. The manifest sets `OTEL_SERVICE_NAME`; standard `OTEL_*` and
`SPLUNK_*` settings remain available.

Send an HTTP request to the application's assigned route and verify a server
span for `splunk-otel-python-example` at the destination.

## SecureApp dependency reports

The bundle includes `secureapp-python-agent` with the same version pin used by
the SecureApp init image. The application does not need to install the extra.
SecureApp reports runtime package dependencies through OpenTelemetry logs.
Use a Collector that routes the `secureapp` instrumentation scope to the
SecureApp event endpoint. See [SecureApp configuration](../../docs/secureapp.md)
for the required endpoint and headers. Setting `SPLUNK_REALM` alone configures
direct traces and metrics; it does not configure SecureApp report routing.

## Agent version

By default, the ZIP bundles the distribution and instrumentation versions pinned
in `docker/requirements.txt` and the SecureApp version pinned in
`docker/requirements-secureapp.txt`. Update those pins and rebuild to change
versions; those files also control the Python init images. When an agent wheel is
supplied, its distribution version replaces the agent pin for that build.

`SPLUNK_OTEL_PYTHON_VERSION` can assert the bundled version during staging. A
mismatch fails staging with an error. It does not download a replacement agent.
This differs from Java's download-at-staging implementation because the Python
payload contains native wheels and matching instrumentation packages.

## Local validation

```sh
.venv/bin/python -m pytest -q tests/test_cloudfoundry_buildpack.py
./tests/smoke/test-cloudfoundry-buildpack.sh \
  deployments/cloudfoundry/buildpack/splunk_otel_python_buildpack-linux.zip
```

The smoke test runs Linux AMD64 in Docker, installs the example application,
runs `supply`, moves the dependency directory, starts the example through the
launcher, verifies the bundled SecureApp agent imports, and checks an exported
Flask server span. It does not validate SecureApp backend library ingestion.
It downloads application requirements during setup. It does not run the
Cloud Foundry lifecycle.

Before using the buildpack beyond a draft, test on PCF: record the platform,
stack, and Python buildpack versions; verify `PATH` setup, request traces,
restaging, restarts, and Gunicorn worker behavior, including worker forks.

## Draft limitations

- Other Python versions, architectures, and stacks are rejected.
- Applications must use the explicit `splunk-otel-python` start command.
- The agent bundle takes priority over application packages with the same names.
  Applications that install OpenTelemetry themselves need separate compatibility
  testing. Package metadata can include both installations.
- Applications with a custom `sitecustomize.py` need separate testing.
- Service bindings, automatic startup injection, profiling, and a fully offline
  application staging workflow have not been validated.
- Top-level package versions are pinned, but transitive dependencies are resolved
  at build time. The resulting ZIP fixes the installed bundle for deployments;
  separate builds can contain different transitive versions.

[java]: https://github.com/signalfx/splunk-otel-java/tree/main/deployments/cloudfoundry/buildpack
[requirements]: ../../docker/requirements.txt
[secureapp-requirements]: ../../docker/requirements-secureapp.txt
[setup]: ../../README.md#get-started
