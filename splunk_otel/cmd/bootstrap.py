import argparse
import pkgutil
import subprocess
import sys
from logging import getLogger

from opentelemetry.instrumentation import bootstrap

from splunk_otel import symbols
from splunk_otel.version import format_version_info

logger = getLogger(__file__)

_INSTRUMENTATION_VERSION = "0.18b1"
_VERSION = "1.0.0rc1"

# target library to desired instrumentor path/versioned package name
instrumentations = {}

for lib, inst in bootstrap.instrumentations.items():
    inst_name, _ = inst.split(">=")
    instrumentations[lib] = "{0}=={1}".format(inst_name, _INSTRUMENTATION_VERSION)


# relevant instrumentors and tracers to uninstall and check for conflicts for target libraries
libraries = bootstrap.libraries

_install_instrumentation = bootstrap._install_package


def _syscall(func):
    def wrapper(package=None):
        try:
            if package:
                return func(package)
            return func()
        except subprocess.SubprocessError as exp:
            cmd = getattr(exp, "cmd", None)
            if cmd:
                msg = 'Error calling system command "{0}"'.format(" ".join(cmd))
            if package:
                msg = '{0} for package "{1}"'.format(msg, package)
            raise RuntimeError(msg)

    return wrapper


@_syscall
def _sys_pip_freeze():
    return (
        subprocess.check_output(
            [
                sys.executable,
                "-m",
                "pip",
                "freeze",
            ]
        )
        .decode()
        .lower()
    )


@_syscall
def _sys_pip_install(package):
    # explicit upgrade strategy to override potential pip config
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "--upgrade-strategy",
            "only-if-needed",
            package,
        ]
    )


@_syscall
def _sys_pip_uninstall(package):
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "uninstall",
            "-y",
            package,
        ]
    )


def _pip_check():
    """Ensures none of the instrumentations have dependency conflicts.
    Clean check reported as:
    'No broken requirements found.'
    Dependency conflicts are reported as:
    'opentelemetry-instrumentation-flask 1.0.1 has requirement opentelemetry-sdk<2.0,>=1.0, but you have opentelemetry-sdk 0.5.'
    To not be too restrictive, we'll only check for relevant packages.
    """
    check_pipe = subprocess.Popen(
        [sys.executable, "-m", "pip", "check"],
        stdout=subprocess.PIPE,
    )
    pip_check = check_pipe.communicate()[0].decode()
    pip_check_lower = pip_check.lower()
    for package_tup in libraries.values():
        for package in package_tup:
            if package.lower() in pip_check_lower:
                raise RuntimeError("Dependency conflict found: {}".format(pip_check))


def _is_installed(library):
    return library in sys.modules or pkgutil.find_loader(library) is not None


def _find_installed_libraries():
    return {k: v for k, v in instrumentations.items() if _is_installed(k)}


def _install_exporter(package):
    _sys_pip_install(package)


def _run_install(instrumentation_packages, exporters):
    for (
        pkg,
        inst,
    ) in instrumentation_packages.items():
        _install_instrumentation(pkg, inst)

    for pkg, inst in exporters.items():
        _install_exporter(inst)

    _pip_check()


def _run_requirements(instrumentation_packages, exporters):
    packages = {}
    packages.update(instrumentation_packages)
    packages.update(exporters)
    print("\n".join(packages.values()), end="")


def _exporter_packages_from_names(exporters):
    return {
        exp: "opentelemetry-exporter-{0}=={1}".format(exp, _VERSION) for exp in exporters
    }


def _compile_package_list(exporters):
    packages = _find_installed_libraries()
    packages.update(_exporter_packages_from_names(exporters))
    return packages


def run() -> None:
    action_install = "install"
    action_requirements = "requirements"

    parser = argparse.ArgumentParser(
        description="""
        opentelemetry-bootstrap detects installed libraries and automatically
        installs the relevant instrumentation packages for them.
        """
    )
    parser.add_argument(
        "--version",
        "-v",
        required=False,
        action="store_true",
        dest="version",
        help="Print version information",
    )
    parser.add_argument(
        "-a",
        "--action",
        choices=[
            action_install,
            action_requirements,
        ],
        default=action_install,
        help="""
        install - uses pip to install the new requirements using to the
                  currently active site-package.
        requirements - prints out the new requirements to stdout. Action can
                       be piped and appended to a requirements.txt file.
        """,
    )
    parser.add_argument(
        "-e",
        "--exporter",
        action="append",
        choices=symbols.trace_exporters,
        help="""
        Installs one or more support telemetry exporters. Supports multiple
        values separated by commas.
        Defaults to `jaeger`.
        """,
    )
    args = parser.parse_args()

    if args.version:
        print(format_version_info())
        return

    cmd = {
        action_install: _run_install,
        action_requirements: _run_requirements,
    }[args.action]
    cmd(
        _find_installed_libraries(),
        _exporter_packages_from_names(args.exporter or [symbols.exporter_jaeger]),
    )
