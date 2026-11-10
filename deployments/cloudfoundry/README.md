# Cloud Foundry buildpack implementation sketch

This document proposes a classic Cloud Foundry buildpack for the Splunk
Distribution of OpenTelemetry Python. It targets applications deployed with
`cf push`, including Pivotal Cloud Foundry (PCF) environments.

This is a design sketch. The files and buildpack name below are proposed. There
is no installable Python buildpack in this directory, and the proposed deployment
has not been tested on Cloud Foundry.

## Java reference

Use the [Splunk Java add-on buildpack][java-buildpack] as the reference for
directory structure, explicit selection, packaging, agent version selection,
and configuration through environment variables.

The Java implementation downloads an agent JAR, copies it into the application,
and writes `config.yml` for the Java buildpack to consume. The Java buildpack runs
last and configures the JVM to load the agent.

Python needs a different installation and startup mechanism:

| Responsibility | Java reference | Proposed Python behavior |
| --- | --- | --- |
| Select the add-on | Explicit buildpack selection | Same |
| Provide the runtime | Java buildpack | Python buildpack |
| Install the agent | Download one JAR | Install or bundle Python packages compatible with the application interpreter |
| Select instrumentation | Agent contains instrumentation | Supply matching instrumentation packages for supported application libraries |
| Enable instrumentation | JVM agent option | Initially use an explicit `opentelemetry-instrument` start command |
| Configure export | Agent environment variables | Existing Python distribution environment variables |
| Package the add-on | ZIP with buildpack scripts | Same structure, with Python installation logic |

The [Splunk integration inside Cloud Foundry's Java buildpack][java-framework]
also supports a `splunk-o11y` service binding. That is a separate integration.
Service binding support can follow the initial environment-variable setup.

## Proposed files

```text
deployments/cloudfoundry/
  README.md
  buildpack/
    manifest.yml         # Buildpack name and supported Cloud Foundry stack
    build.sh             # Package the buildpack ZIP
    bin/
      detect             # Exit 1: require explicit selection, as Java does
      supply             # Stage the agent payload in this buildpack's deps directory
      finalize           # Reject use as the final buildpack with a clear error
  example/
    app.py               # One Flask route
    requirements.txt     # Flask and Gunicorn; agent supplied by the add-on
    manifest.yml         # Buildpacks, start command, and export configuration
```

Unlike Java's no-op `finalize`, the proposed Python `finalize` would fail when
the add-on is selected last. The language buildpack must configure the runtime
and application start command.

The intended buildpack order follows Java:

```text
splunk_otel_python_buildpack -> python_buildpack
```

This order is a design goal, not a validated deployment command.

## Installation timing: the first decision to test

[Cloud Foundry runs each supply buildpack before the final buildpack][cf-buildpacks].
Therefore, the Splunk add-on cannot assume that Python, pip, or the application's
installed packages exist when its `supply` script runs.

The add-on must write its payload under its own `deps/<index>` directory.
Do not copy Java's writes into the application directory without checking the
target platform's restrictions. Cloud Foundry documents that supply buildpacks
must not modify other buildpack or application directories.

Two installation approaches need evaluation:

| Approach | What needs proof |
| --- | --- |
| Prebuilt agent and instrumentation bundle, staged before the Python buildpack | Select compatible Python wheels; expose the bundle at launch; avoid conflicts with application packages |
| Install after the Python buildpack installs application packages | Find a supported integration point that can install agent packages and run bootstrap during staging |

The first approach follows Java's independent payload model most closely. The
[existing Python init image][python-image] is a reference for bundling packages
and selecting dependencies for an interpreter. Cloud Foundry still needs its
own staging and launch integration.

The second approach permits instrumentation selection from installed packages.
The [Python buildpack's application hooks][python-hooks] include a
`bin/post_compile` hook. Test that hook as an application-owned experiment;
do not assume a preceding supply buildpack can create or replace it.

Do not install packages at application startup. Resolve packages during staging
or while building the payload so restarts do not require package downloads.

## Lifecycle pseudocode

This pseudocode describes responsibilities; it is not an executable supply script.
The installation approach above must be selected before implementing these steps.

```text
supply(build_dir, cache_dir, deps_dir, index):
    validate arguments and selected agent version
    obtain the versioned agent payload, using the cache where possible
    verify the payload checksum
    stage the payload under deps_dir/index
    stage launch configuration under deps_dir/index
    leave application files and other buildpack dependencies unchanged

launch setup, after the Python buildpack's environment setup:
    check that the application interpreter is supported
    expose the selected agent packages and instrumentation command
    retain the application's existing package search paths
    run the explicit application command through opentelemetry-instrument
```

Verify launch script ordering: the Python buildpack sets `PYTHONPATH` itself.
Also verify that all paths work after Cloud Foundry moves staged files into the
application container. An absolute staging path must not become a launch path.

## First experiment

First establish a working Python instrumentation baseline on Cloud Foundry.
This experiment uses application-owned setup and does not validate the add-on.

1. Deploy one Flask application using the installed Python buildpack.
2. Include a selected `splunk-opentelemetry` version in the application's
   requirements. Use a Python version supported by that release and the platform.
3. In an application-owned staging hook, run
   `opentelemetry-bootstrap -a install` after application packages are installed.
   Confirm the hook timing on the target Python buildpack version.
4. Start the application with
   `opentelemetry-instrument gunicorn --bind 0.0.0.0:$PORT app:app`.
5. Set `OTEL_SERVICE_NAME` and an explicit export destination. Use a reachable
   Collector, or configure direct export with `SPLUNK_REALM` and
   `SPLUNK_ACCESS_TOKEN`. A Collector is not installed by this proposed add-on.
6. Send a request and verify that a server span reaches the destination.

Then move installation into the selected buildpack approach. Remove the agent
requirement and experimental hook from the application, repeat the request,
and verify the same result. That second deployment tests the add-on's behavior.

## Validation before calling the buildpack usable

- Record the platform version, stack, Python buildpack version, and interpreter.
- Prove staging order, package visibility, and launch configuration ordering.
- Verify a request trace and the configured service name.
- Restage and restart the application; confirm startup performs no pip downloads.
- Verify that the selected version is reported and that changing it changes the
  installed payload without reusing an incompatible cache entry.
- Check dependency conflicts, unsupported interpreters, and failed downloads.
- Test Gunicorn workers separately, including initialization after worker forks.
- Test an application that already supplies OpenTelemetry packages.
- Define offline packaging and private package-index support before claiming them.

## Initial scope

Start with one Linux stack, one CPython minor version, Flask, and an explicit
instrumented start command. Select versions after inspecting the test platform.
Use a pinned agent version for the experiment.

Automatic startup injection, Django, service bindings, Collector deployment,
profiling, and offline packaging need separate validation. An unchanged start
command may eventually use Python startup injection, but that requires testing
application `sitecustomize.py` behavior and package search ordering.

[java-buildpack]: https://github.com/signalfx/splunk-otel-java/tree/main/deployments/cloudfoundry/buildpack
[java-framework]: https://github.com/cloudfoundry/java-buildpack/blob/main/docs/framework-splunk_otel_java_agent.md
[cf-buildpacks]: https://docs.cloudfoundry.org/buildpacks/understand-buildpacks.html
[python-image]: ../../docker/README.md
[python-hooks]: https://github.com/cloudfoundry/python-buildpack/blob/master/src/python/hooks/hooks_app.go
