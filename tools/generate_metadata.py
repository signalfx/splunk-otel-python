"""Generate Splunk OpenTelemetry Python release metadata.

Intended to be run after a release. Upload the generated YAML file as a
GitHub Release asset alongside the wheel, sdist, checksums, and signature.
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - used on Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - best effort fallback for tool use
        from pip._vendor import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OTEL_PYTHON_SOURCE = "https://github.com/open-telemetry/opentelemetry-python"
OTEL_PYTHON_CONTRIB_SOURCE = "https://github.com/open-telemetry/opentelemetry-python-contrib"
PYPI_PROJECT = "https://pypi.org/project"

STABLE = "stable"
EXPERIMENTAL = "experimental"
COMMUNITY = "community"
SUPPORTED = "supported"

SETTING_EXPORTER = "exporter"
SETTING_GENERAL = "general"
SETTING_INSTRUMENTATION = "instrumentation"
SETTING_LIMITS = "limits"
SETTING_OPAMP = "opamp"
SETTING_PROFILING = "profiling"
SETTING_RESOURCE = "resource"
SETTING_SAMPLER = "sampler"
SETTING_TRACE_PROPAGATION = "trace propagation"

TYPE_BOOLEAN = "boolean"
TYPE_DOUBLE = "double"
TYPE_INT = "int"
TYPE_STRING = "string"

METRIC_BUNDLED = "APM bundled, if data points for the metric contain `telemetry.sdk.language` attribute."

REQ_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9_.-]+)\s*(?P<specifier>.*?)(?:\s*;\s*.*)?$")
PRERELEASE_RE = re.compile(r"(?:\d(?:a|b|rc)\d|alpha|beta|dev)", re.IGNORECASE)

SETTINGS: list[dict[str, str]] = [
    {
        "property": "otel.traces.exporter",
        "env": "OTEL_TRACES_EXPORTER",
        "description": "Comma-separated list of trace exporters. The Splunk distribution defaults to OTLP.",
        "default": "otlp",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.metrics.exporter",
        "env": "OTEL_METRICS_EXPORTER",
        "description": "Comma-separated list of metric exporters. The Splunk distribution defaults to OTLP.",
        "default": "otlp",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.logs.exporter",
        "env": "OTEL_LOGS_EXPORTER",
        "description": "Comma-separated list of log exporters. The Splunk distribution defaults to OTLP.",
        "default": "otlp",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "splunk.realm",
        "env": "SPLUNK_REALM",
        "description": (
            "Splunk Observability Cloud realm. When set, OTLP traces and metrics "
            "endpoints default to the realm ingest endpoints."
        ),
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "splunk.access.token",
        "env": "SPLUNK_ACCESS_TOKEN",
        "description": ("Splunk authentication token added to OTLP exporter headers as x-sf-token when set."),
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.protocol",
        "env": "OTEL_EXPORTER_OTLP_PROTOCOL",
        "description": "OTLP exporter transport protocol.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.traces.protocol",
        "env": "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
        "description": "OTLP traces exporter transport protocol.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.metrics.protocol",
        "env": "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL",
        "description": "OTLP metrics exporter transport protocol.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.logs.protocol",
        "env": "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL",
        "description": "OTLP logs exporter transport protocol.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.headers",
        "env": "OTEL_EXPORTER_OTLP_HEADERS",
        "description": "Comma-separated list of additional OTLP exporter headers.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.endpoint",
        "env": "OTEL_EXPORTER_OTLP_ENDPOINT",
        "description": "OTLP endpoint used as the base endpoint for traces, metrics, and logs.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.traces.endpoint",
        "env": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "description": (
            "OTLP traces endpoint. When SPLUNK_REALM is set, the default is the "
            "Splunk trace ingest endpoint for that realm."
        ),
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.metrics.endpoint",
        "env": "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "description": (
            "OTLP metrics endpoint. When SPLUNK_REALM is set, the default is the "
            "Splunk metric ingest endpoint for that realm."
        ),
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.exporter.otlp.logs.endpoint",
        "env": "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "description": ("OTLP logs endpoint. Profiling can use SPLUNK_PROFILER_LOGS_ENDPOINT to set this endpoint."),
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_EXPORTER,
    },
    {
        "property": "otel.attribute.count.limit",
        "env": "OTEL_ATTRIBUTE_COUNT_LIMIT",
        "description": (
            "Maximum number of attributes allowed on spans, events, links, and "
            "resources. The Splunk distribution leaves this unlimited by default."
        ),
        "default": "",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.attribute.value.length.limit",
        "env": "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT",
        "description": "Maximum length of attribute values.",
        "default": "12000",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.span.attribute.count.limit",
        "env": "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT",
        "description": (
            "Maximum number of attributes allowed on a span. The Splunk distribution leaves this unlimited by default."
        ),
        "default": "",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.span.event.count.limit",
        "env": "OTEL_SPAN_EVENT_COUNT_LIMIT",
        "description": (
            "Maximum number of events allowed on a span. The Splunk distribution leaves this unlimited by default."
        ),
        "default": "",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.event.attribute.count.limit",
        "env": "OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT",
        "description": (
            "Maximum number of attributes allowed on a span event. The Splunk "
            "distribution leaves this unlimited by default."
        ),
        "default": "",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.link.attribute.count.limit",
        "env": "OTEL_LINK_ATTRIBUTE_COUNT_LIMIT",
        "description": (
            "Maximum number of attributes allowed on a span link. The Splunk "
            "distribution leaves this unlimited by default."
        ),
        "default": "",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.span.link.count.limit",
        "env": "OTEL_SPAN_LINK_COUNT_LIMIT",
        "description": "Maximum number of links allowed on a span.",
        "default": "1000",
        "type": TYPE_INT,
        "category": SETTING_LIMITS,
    },
    {
        "property": "otel.experimental.resource.detectors",
        "env": "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS",
        "description": "Comma-separated list of resource detectors enabled by the SDK.",
        "default": "host,process",
        "type": TYPE_STRING,
        "category": SETTING_RESOURCE,
    },
    {
        "property": "otel.resource.attributes",
        "env": "OTEL_RESOURCE_ATTRIBUTES",
        "description": "Comma-separated resource attributes in key=value form.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_RESOURCE,
    },
    {
        "property": "otel.service.name",
        "env": "OTEL_SERVICE_NAME",
        "description": "Logical service name. Defaults to unnamed-python-service in this distribution.",
        "default": "unnamed-python-service",
        "type": TYPE_STRING,
        "category": SETTING_RESOURCE,
    },
    {
        "property": "otel.traces.sampler",
        "env": "OTEL_TRACES_SAMPLER",
        "description": "Sampler used for traces.",
        "default": "always_on",
        "type": TYPE_STRING,
        "category": SETTING_SAMPLER,
    },
    {
        "property": "splunk.trace-response-header.enabled",
        "env": "SPLUNK_TRACE_RESPONSE_HEADER_ENABLED",
        "description": "Activates the Splunk Server-Timing trace response header propagator.",
        "default": "true",
        "type": TYPE_BOOLEAN,
        "category": SETTING_TRACE_PROPAGATION,
    },
    {
        "property": "splunk.otel.system.metrics.enabled",
        "env": "SPLUNK_OTEL_SYSTEM_METRICS_ENABLED",
        "description": "Activates system metrics instrumentation when set to true.",
        "default": "false",
        "type": TYPE_BOOLEAN,
        "category": SETTING_INSTRUMENTATION,
    },
    {
        "property": "otel.python.disabled.instrumentations",
        "env": "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS",
        "description": "Comma-separated list of Python auto-instrumentations to disable.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_INSTRUMENTATION,
    },
    {
        "property": "splunk.profiler.enabled",
        "env": "SPLUNK_PROFILER_ENABLED",
        "description": "Activates continuous profiling.",
        "default": "false",
        "type": TYPE_BOOLEAN,
        "category": SETTING_PROFILING,
    },
    {
        "property": "splunk.profiler.call.stack.interval",
        "env": "SPLUNK_PROFILER_CALL_STACK_INTERVAL",
        "description": "Frequency in milliseconds for continuous profiling call stack collection.",
        "default": "1000",
        "type": TYPE_INT,
        "category": SETTING_PROFILING,
    },
    {
        "property": "splunk.profiler.logs.endpoint",
        "env": "SPLUNK_PROFILER_LOGS_ENDPOINT",
        "description": "Collector endpoint for profiling logs.",
        "default": "",
        "type": TYPE_STRING,
        "category": SETTING_PROFILING,
    },
    {
        "property": "splunk.snapshot.profiler.enabled",
        "env": "SPLUNK_SNAPSHOT_PROFILER_ENABLED",
        "description": "Activates call graph snapshot profiling.",
        "default": "false",
        "type": TYPE_BOOLEAN,
        "category": SETTING_PROFILING,
    },
    {
        "property": "splunk.snapshot.sampling.interval",
        "env": "SPLUNK_SNAPSHOT_SAMPLING_INTERVAL",
        "description": "Frequency in milliseconds for snapshot profiling stack sample collection.",
        "default": "10",
        "type": TYPE_INT,
        "category": SETTING_PROFILING,
    },
    {
        "property": "splunk.snapshot.selection.probability",
        "env": "SPLUNK_SNAPSHOT_SELECTION_PROBABILITY",
        "description": "Fraction of traces selected for snapshot profiling.",
        "default": "0.01",
        "type": TYPE_DOUBLE,
        "category": SETTING_PROFILING,
    },
    {
        "property": "splunk.opamp.enabled",
        "env": "SPLUNK_OPAMP_ENABLED",
        "description": "Activates the OpAMP client.",
        "default": "false",
        "type": TYPE_BOOLEAN,
        "category": SETTING_OPAMP,
    },
    {
        "property": "splunk.opamp.endpoint",
        "env": "SPLUNK_OPAMP_ENDPOINT",
        "description": "OpAMP server endpoint.",
        "default": "http://localhost:4320/v1/opamp",
        "type": TYPE_STRING,
        "category": SETTING_OPAMP,
    },
    {
        "property": "splunk.opamp.polling.interval",
        "env": "SPLUNK_OPAMP_POLLING_INTERVAL",
        "description": "OpAMP polling interval in milliseconds.",
        "default": "30000",
        "type": TYPE_INT,
        "category": SETTING_OPAMP,
    },
]

RESOURCE_DETECTORS = [
    {
        "key": "host",
        "description": "Host resource detector.",
        "attributes": [{"id": "host.name"}, {"id": "host.arch"}],
        "stability": EXPERIMENTAL,
        "support": COMMUNITY,
    },
    {
        "key": "os",
        "description": "Operating system resource detector.",
        "attributes": [{"id": "os.type"}, {"id": "os.version"}],
        "stability": EXPERIMENTAL,
        "support": COMMUNITY,
    },
    {
        "key": "process",
        "description": "Process resource detector.",
        "attributes": [
            {"id": "process.runtime.description"},
            {"id": "process.runtime.name"},
            {"id": "process.runtime.version"},
            {"id": "process.pid"},
            {"id": "process.executable.name"},
            {"id": "process.executable.path"},
            {"id": "process.command"},
            {"id": "process.command_line"},
            {"id": "process.command_args"},
            {"id": "process.parent_pid"},
            {"id": "process.owner"},
        ],
        "stability": EXPERIMENTAL,
        "support": COMMUNITY,
    },
    {
        "key": "otel",
        "description": "Environment variable resource detector.",
        "attributes": [{"id": "service.name"}, {"id": "OTEL_RESOURCE_ATTRIBUTES keys"}],
        "stability": STABLE,
        "support": COMMUNITY,
    },
]


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


def load_toml_bytes(content: bytes) -> dict[str, Any]:
    return tomllib.loads(content.decode())


def parse_project_version(project_root: Path) -> str:
    about = project_root / "src" / "splunk_otel" / "__about__.py"
    module = ast.parse(about.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__version__"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    return node.value.value
    msg = f"could not find __version__ in {about}"
    raise RuntimeError(msg)


def parse_requirement(requirement: str) -> tuple[str, str]:
    match = REQ_RE.match(requirement)
    if not match:
        msg = f"unsupported dependency requirement: {requirement!r}"
        raise ValueError(msg)
    name = match.group("name")
    specifier = match.group("specifier").strip().replace(" ", "")
    specifier = specifier.removeprefix("==")
    return name, specifier


def dependency(
    name: str,
    version: str,
    stability: str = STABLE,
    source_href: str | None = None,
    package_href: str | None = None,
) -> dict[str, str]:
    result = {"name": name}
    if source_href is not None:
        result["source_href"] = source_href
    if package_href is not None:
        result["package_href"] = package_href
    result["version"] = version
    result["stability"] = stability
    return result


def dependency_stability(version_or_specifier: str) -> str:
    if PRERELEASE_RE.search(version_or_specifier):
        return EXPERIMENTAL
    return STABLE


def source_href_for_package(name: str) -> str | None:
    if name in {"opentelemetry-api", "opentelemetry-sdk", "opentelemetry-semantic-conventions"}:
        return f"{OTEL_PYTHON_SOURCE}/tree/main/{name}"
    if name.startswith("opentelemetry-exporter-"):
        return f"{OTEL_PYTHON_SOURCE}/tree/main/exporter/{name}"
    if name.startswith("opentelemetry-propagator-"):
        return f"{OTEL_PYTHON_SOURCE}/tree/main/propagator/{name}"
    if name == "opentelemetry-instrumentation":
        return f"{OTEL_PYTHON_CONTRIB_SOURCE}/tree/main/opentelemetry-instrumentation"
    if name.startswith("opentelemetry-instrumentation-"):
        return f"{OTEL_PYTHON_CONTRIB_SOURCE}/tree/main/instrumentation/{name}"
    if name == "opentelemetry-opamp-client":
        return f"{OTEL_PYTHON_CONTRIB_SOURCE}/tree/main/opamp/{name}"
    return None


def build_dependencies(project: dict[str, Any]) -> list[dict[str, str]]:
    direct = [parse_requirement(req) for req in project["dependencies"]]
    versions = dict(direct)
    otel_version = versions["opentelemetry-api"]
    otel_contrib_version = versions["opentelemetry-instrumentation"]

    result = [
        dependency(
            "OpenTelemetry Python",
            otel_version,
            STABLE,
            source_href=OTEL_PYTHON_SOURCE,
        ),
        dependency(
            "OpenTelemetry Python Contrib",
            otel_contrib_version,
            dependency_stability(otel_contrib_version),
            source_href=OTEL_PYTHON_CONTRIB_SOURCE,
        ),
    ]

    for name, specifier in direct:
        result.append(
            dependency(
                name,
                specifier,
                dependency_stability(specifier),
                source_href=source_href_for_package(name),
                package_href=f"{PYPI_PROJECT}/{name}/",
            )
        )
    return result


def contrib_archive_url(version: str) -> str:
    if version.endswith(".dev"):
        return f"{OTEL_PYTHON_CONTRIB_SOURCE}/archive/refs/heads/main.tar.gz"
    return f"{OTEL_PYTHON_CONTRIB_SOURCE}/archive/refs/tags/v{version}.tar.gz"


def iter_contrib_pyprojects_from_root(contrib_root: Path) -> Iterable[tuple[str, dict[str, Any]]]:
    search_roots = [
        contrib_root / "instrumentation",
        contrib_root / "instrumentation-genai",
    ]
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for pyproject in sorted(search_root.glob("opentelemetry-instrumentation-*/pyproject.toml")):
            yield str(pyproject.relative_to(contrib_root)), load_toml(pyproject)


def iter_contrib_pyprojects_from_archive(version: str) -> Iterable[tuple[str, dict[str, Any]]]:
    url = contrib_archive_url(version)
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        archive = response.read()

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in sorted(tar.getmembers(), key=lambda item: item.name):
            path = member.name
            if not path.endswith("/pyproject.toml"):
                continue
            if "/instrumentation/opentelemetry-instrumentation-" not in path and (
                "/instrumentation-genai/opentelemetry-instrumentation-" not in path
            ):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            yield path, load_toml_bytes(extracted.read())


def component_name(requirement: str) -> str:
    name, _specifier = parse_requirement(requirement)
    return name


def build_instrumentation(_path: str, pyproject: dict[str, Any]) -> dict[str, Any] | None:
    project = pyproject["project"]
    entry_points = project.get("entry-points", {}).get("opentelemetry_instrumentor", {})
    if not entry_points:
        return None

    optional_dependencies = project.get("optional-dependencies", {})
    instruments = optional_dependencies.get("instruments", [])
    package_name = project["name"]

    if instruments:
        components = [
            {
                "name": component_name(requirement),
                "supported_versions": requirement,
            }
            for requirement in instruments
        ]
    else:
        components = [{"name": package_name}]

    result: dict[str, Any] = {
        "keys": sorted(entry_points.keys()),
        "instrumented_components": components,
        "description": project.get("description", ""),
        "stability": EXPERIMENTAL,
        "support": COMMUNITY,
    }
    if package_name == "opentelemetry-instrumentation-system-metrics":
        result["support"] = SUPPORTED
        result["signals"] = [{"metrics": system_metrics()}]
    return result


def build_instrumentations(
    otel_contrib_version: str,
    contrib_root: Path | None = None,
    *,
    allow_download: bool = True,
) -> list[dict[str, Any]]:
    if contrib_root is not None:
        pyprojects = iter_contrib_pyprojects_from_root(contrib_root)
    else:
        env_root = os.environ.get("OTEL_PYTHON_CONTRIB_ROOT")
        if env_root:
            pyprojects = iter_contrib_pyprojects_from_root(Path(env_root))
        elif allow_download:
            pyprojects = iter_contrib_pyprojects_from_archive(otel_contrib_version)
        else:
            msg = "set --contrib-root or allow network download"
            raise RuntimeError(msg)

    instrumentations = [
        instrumentation
        for path, pyproject in pyprojects
        if (instrumentation := build_instrumentation(path, pyproject)) is not None
    ]
    return sorted(instrumentations, key=lambda item: ",".join(item["keys"]))


def metric(name: str, instrument: str, description: str, category_notes: str) -> dict[str, str]:
    return {
        "metric_name": name,
        "instrument": instrument,
        "description": description,
        "category_notes": category_notes,
    }


def build_metrics() -> list[dict[str, str]]:
    return []


def system_metrics() -> list[dict[str, str]]:
    return [
        metric("system.cpu.time", "counter", "System CPU time.", METRIC_BUNDLED),
        metric("system.cpu.utilization", "gauge", "System CPU utilization.", METRIC_BUNDLED),
        metric("system.memory.usage", "gauge", "System memory usage.", METRIC_BUNDLED),
        metric("system.memory.utilization", "gauge", "System memory utilization.", METRIC_BUNDLED),
        metric("system.swap.usage", "gauge", "System swap usage.", METRIC_BUNDLED),
        metric("system.swap.utilization", "gauge", "System swap utilization.", METRIC_BUNDLED),
        metric("system.disk.io", "counter", "System disk IO.", METRIC_BUNDLED),
        metric("system.disk.operations", "counter", "System disk operations.", METRIC_BUNDLED),
        metric("system.disk.time", "counter", "System disk time.", METRIC_BUNDLED),
        metric(
            "system.network.dropped_packets",
            "counter",
            "System network dropped packets.",
            METRIC_BUNDLED,
        ),
        metric("system.network.packets", "counter", "System network packets.", METRIC_BUNDLED),
        metric("system.network.errors", "counter", "System network errors.", METRIC_BUNDLED),
        metric("system.network.io", "counter", "System network IO.", METRIC_BUNDLED),
        metric(
            "system.network.connections",
            "updowncounter",
            "System network connections.",
            METRIC_BUNDLED,
        ),
        metric("system.thread_count", "gauge", "System active thread count.", METRIC_BUNDLED),
        metric("process.cpu.time", "counter", "Total CPU seconds by state.", METRIC_BUNDLED),
        metric("process.cpu.utilization", "gauge", "Process CPU utilization.", METRIC_BUNDLED),
        metric("process.context_switches", "counter", "Process context switches.", METRIC_BUNDLED),
        metric("process.memory.usage", "updowncounter", "Physical memory in use.", METRIC_BUNDLED),
        metric("process.memory.virtual", "updowncounter", "Committed virtual memory.", METRIC_BUNDLED),
        metric(
            "process.open_file_descriptor.count",
            "updowncounter",
            "Open file descriptor count.",
            METRIC_BUNDLED,
        ),
        metric("process.thread.count", "updowncounter", "Process thread count.", METRIC_BUNDLED),
        metric("process.disk.io", "counter", "Disk bytes transferred for the process.", METRIC_BUNDLED),
    ]


def generate_metadata(
    project_root: Path = PROJECT_ROOT,
    contrib_root: Path | None = None,
    *,
    allow_download: bool = True,
) -> dict[str, Any]:
    pyproject = load_toml(project_root / "pyproject.toml")
    project = pyproject["project"]
    direct = dict(parse_requirement(req) for req in project["dependencies"])
    otel_contrib_version = direct["opentelemetry-instrumentation"]

    return {
        "component": "Splunk Distribution of OpenTelemetry Python",
        "version": parse_project_version(project_root),
        "dependencies": build_dependencies(project),
        "settings": SETTINGS,
        "metrics": build_metrics(),
        "instrumentations": build_instrumentations(
            otel_contrib_version,
            contrib_root,
            allow_download=allow_download,
        ),
        "resource_detectors": RESOURCE_DETECTORS,
    }


def dump_yaml(data: Any) -> str:
    lines: list[str] = []
    emit_yaml(data, lines, 0)
    return "\n".join(lines) + "\n"


def emit_yaml(data: Any, lines: list[str], indent: int) -> None:
    if isinstance(data, dict):
        emit_mapping(data, lines, indent)
    elif isinstance(data, list):
        emit_sequence(data, lines, indent)
    else:
        lines.append(" " * indent + format_scalar(data))


def emit_mapping(data: dict[str, Any], lines: list[str], indent: int) -> None:
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            if value:
                lines.append(f"{prefix}{key}:")
                emit_mapping(value, lines, indent + 2)
            else:
                lines.append(f"{prefix}{key}: {{}}")
        elif isinstance(value, list):
            if value:
                lines.append(f"{prefix}{key}:")
                emit_sequence(value, lines, indent + 2)
            else:
                lines.append(f"{prefix}{key}: []")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{prefix}{key}: |-")
            lines.extend(" " * (indent + 2) + line for line in value.splitlines())
        else:
            lines.append(f"{prefix}{key}: {format_scalar(value)}")


def emit_sequence(data: list[Any], lines: list[str], indent: int) -> None:
    prefix = " " * indent
    for item in data:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{prefix}- {{}}")
                continue
            first = True
            for key, value in item.items():
                marker = "-" if first else " "
                first = False
                if isinstance(value, dict):
                    if value:
                        lines.append(f"{prefix}{marker} {key}:")
                        emit_mapping(value, lines, indent + 4)
                    else:
                        lines.append(f"{prefix}{marker} {key}: {{}}")
                elif isinstance(value, list):
                    if value:
                        lines.append(f"{prefix}{marker} {key}:")
                        emit_sequence(value, lines, indent + 4)
                    else:
                        lines.append(f"{prefix}{marker} {key}: []")
                elif isinstance(value, str) and "\n" in value:
                    lines.append(f"{prefix}{marker} {key}: |-")
                    lines.extend(" " * (indent + 4) + line for line in value.splitlines())
                else:
                    lines.append(f"{prefix}{marker} {key}: {format_scalar(value)}")
        elif isinstance(item, list):
            lines.append(f"{prefix}-")
            emit_sequence(item, lines, indent + 2)
        else:
            lines.append(f"{prefix}- {format_scalar(item)}")


def format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return "''"
    return "'" + text.replace("'", "''") + "'"


def write_output(output: str, metadata: dict[str, Any]) -> None:
    yaml_text = dump_yaml(metadata)
    if output == "-":
        sys.stdout.write(yaml_text)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Path to the splunk-otel-python repository root.",
    )
    parser.add_argument(
        "--contrib-root",
        type=Path,
        default=None,
        help="Optional local opentelemetry-python-contrib checkout to avoid network access.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Fail instead of downloading OpenTelemetry Python Contrib metadata.",
    )
    parser.add_argument(
        "--output",
        default="metadata.yaml",
        help="Output file path, or '-' for stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    metadata = generate_metadata(
        args.project_root,
        args.contrib_root,
        allow_download=not args.no_download,
    )
    write_output(args.output, metadata)
    sys.stderr.write(
        "generated "
        f"{args.output} with "
        f"{len(metadata['dependencies'])} dependencies, "
        f"{len(metadata['settings'])} settings, "
        f"{len(metadata['instrumentations'])} instrumentations, and "
        f"{len(metadata['resource_detectors'])} resource detectors\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
