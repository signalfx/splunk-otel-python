import yaml

from metadata import aggregate_yamls


def test_extract_instrumentation_fields_minimal():
    data = {"name": "TestInstr"}
    instr = aggregate_yamls.extract_instrumentation_fields(data)
    assert instr["keys"] == ["testinstr"]
    assert instr["instrumented_components"][0]["name"] == "TestInstr"
    assert instr["stability"] == "stable"
    assert instr["support"] == "official"
    assert instr["signals"] == []


def test_extract_instrumentation_fields_full():
    data = {
        "keys": ["foo"],
        "instrumented_components": [{"name": "Bar", "supported_versions": "2.0"}],
        "stability": "beta",
        "support": "community",
        "spans": [
            {"name": "span1", "attributes": [{"name": "attr1"}, {"name": "attr2"}]},
            {"name": "span2"},
        ],
    }
    instr = aggregate_yamls.extract_instrumentation_fields(data)
    assert instr["keys"] == ["foo"]
    assert instr["instrumented_components"][0]["name"] == "Bar"
    assert instr["stability"] == "beta"
    assert instr["support"] == "community"
    assert instr["signals"][0]["spans"][0]["attributes"] == ["attr1", "attr2"]


def test_main_creates_yaml(tmp_path, monkeypatch):
    yamls_dir = tmp_path / "yamls"
    yamls_dir.mkdir()
    # Create a sample yaml file
    sample_yaml = yamls_dir / "test.yaml"
    sample_yaml.write_text("""
name: testinstr
instrumented_components:
  - name: testcomp
    supported_versions: 1.0
stability: beta
support: community
spans:
  - name: span1
    attributes:
      - name: attr1
      - name: attr2
  - name: span2
""")
    # Patch yamls_dir and output_path in main
    out_yaml = tmp_path / "splunk-otel-python-metadata.yaml"
    monkeypatch.setattr(aggregate_yamls, "find_all_yaml_files", lambda _: [sample_yaml])

    def load_yaml_file_with_ctx(path):
        with open(path) as f:
            return yaml.safe_load(f)

    monkeypatch.setattr(aggregate_yamls, "load_yaml_file", load_yaml_file_with_ctx)
    monkeypatch.setattr(aggregate_yamls.os.path, "dirname", lambda _: str(tmp_path))
    monkeypatch.setattr(aggregate_yamls.os.path, "abspath", lambda x: str(x))
    # Run main
    aggregate_yamls.main()
    # Check output file
    assert out_yaml.exists()
    with open(out_yaml) as f:
        meta = yaml.safe_load(f)
    assert meta["component"] == "Splunk Distribution of OpenTelemetry Python"
    assert meta["instrumentations"][0]["keys"] == ["testinstr"]
    assert "settings" in meta
    assert isinstance(meta["settings"], list)
