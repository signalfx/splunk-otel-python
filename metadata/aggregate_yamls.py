import ast
import glob
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from splunk_otel.env import DEFAULTS


def find_all_yaml_files(yamls_dir):
    yamls_dir = Path(yamls_dir)
    return sorted([f for f in yamls_dir.iterdir() if f.is_file() and f.suffix == ".yaml"], key=lambda p: p.name)


def load_yaml_file(path):
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return None


def extract_instrumentation_fields(data):
    instr = {}
    if "keys" in data:
        instr["keys"] = data["keys"]
    elif "instrumentation_name" in data:
        instr["keys"] = [data["instrumentation_name"]]
    elif "name" in data:
        instr["keys"] = [data["name"].lower()]
    else:
        instr["keys"] = []

    if "instrumented_components" in data:
        instr["instrumented_components"] = data["instrumented_components"]
    elif "name" in data:
        instr["instrumented_components"] = [
            {"name": data["name"], "supported_versions": data.get("supported_versions", "varies")}
        ]
    else:
        instr["instrumented_components"] = []

    instr["stability"] = data.get("stability", "stable")
    instr["support"] = data.get("support", "official")

    def norm(attrs):
        return [a["name"] if isinstance(a, dict) and set(a) == {"name"} else a for a in (attrs or [])]

    signals = []
    for key in ("spans",):
        if key in data:
            spans = [
                dict(span, attributes=norm(span.get("attributes"))) if "attributes" in span else dict(span)
                for span in data[key]
            ]
            signals.append({"spans": spans})
    if not signals and "signals" in data:
        for s in data["signals"]:
            if "spans" in s:
                spans = [
                    dict(span, attributes=norm(span.get("attributes"))) if "attributes" in span else dict(span)
                    for span in s["spans"]
                ]
                signals.append({"spans": spans})
    instr["signals"] = signals

    return instr


def main():
    yamls_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generator", "yamls")
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splunk-otel-python-metadata.yaml")

    component = "Splunk Distribution of OpenTelemetry Python"
    version = "1.0.0"
    dependencies = []
    instrumentations = []

    for yaml_file in find_all_yaml_files(yamls_dir):
        data = load_yaml_file(yaml_file)
        if data:
            instr = extract_instrumentation_fields(data)
            instrumentations.append(instr)

    # Extract all OTEL_ and SPLUNK_ env var constants from src/splunk_otel
    settings = []
    env_vars = set()
    for pyfile in glob.glob(os.path.join(os.path.dirname(__file__), "../src/splunk_otel/**/*.py"), recursive=True):
        with open(pyfile) as f:
            tree = ast.parse(f.read(), filename=pyfile)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)
                            and (node.value.value.startswith("OTEL_") or node.value.value.startswith("SPLUNK_"))
                        ):
                            env_vars.add(node.value.value)
    # Add also those from DEFAULTS (for default values)
    env_vars.update(DEFAULTS.keys())
    seen = set()
    for env in sorted(env_vars):
        if env in seen:
            continue
        seen.add(env)
        # Auto property: convert env to lower, replace _ with . and remove leading otel_/splunk_
        prop = env.lower()
        if prop.startswith("otel_"):
            prop = prop.replace("otel_", "otel.", 1)
        elif prop.startswith("splunk_"):
            prop = prop.replace("splunk_", "splunk.", 1)
        prop = prop.replace("_", ".")
        # Auto type
        if "enabled" in env.lower():
            typ = "boolean"
        elif any(x in env.lower() for x in ["interval", "limit", "count"]):
            typ = "int"
        else:
            typ = "string"
        # Auto category
        if "exporter" in env.lower():
            cat = "exporter"
        elif "instrumentation" in env.lower():
            cat = "instrumentation"
        elif "splunk" in env.lower():
            cat = "splunk"
        else:
            cat = "general"
        # Auto description
        if typ == "boolean":
            desc = f"Enable or disable {prop.replace('.', ' ')}."
        elif typ == "int":
            desc = f"Integer value for {prop.replace('.', ' ')}."
        else:
            desc = f"Value for {prop.replace('.', ' ')}."
        settings.append(
            {
                "property": prop,
                "env": env,
                "description": desc,
                "default": DEFAULTS.get(env, ""),
                "type": typ,
                "category": cat,
            }
        )
    # Sort settings by property for more readable YAML
    settings = sorted(settings, key=lambda s: s["property"])

    final_metadata = {
        "component": component,
        "version": version,
        "dependencies": dependencies,
        "settings": settings,
        "instrumentations": instrumentations,
    }

    class IndentDumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):  # noqa: FBT002
            return super().increase_indent(flow, False)

    with open(output_path, "w") as f:
        yaml.dump(final_metadata, f, default_flow_style=False, sort_keys=False, Dumper=IndentDumper, indent=2)


if __name__ == "__main__":
    main()
