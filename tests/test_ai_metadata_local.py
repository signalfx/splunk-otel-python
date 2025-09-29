import os
import sys
import textwrap

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../metadata/generator"))
)
import ai_metadata_generator

# Constants for test values
EXPECTED_TOKEN_10 = 10
EXPECTED_TOKEN_25 = 25


def test_env_vars_found():
    code = """
    foo = os.getenv("OTEL_FOO")
    bar = os.environ.get('SPLUNK_BAR')
    # OTEL_BAZ in a comment
    """
    vars_found = ai_metadata_generator.extract_env_vars_from_code(code)
    assert set(vars_found) == {"OTEL_FOO", "SPLUNK_BAR", "OTEL_BAZ"}


def test_env_vars_empty():
    code = "print('no envs here')"
    vars_found = ai_metadata_generator.extract_env_vars_from_code(code)
    assert vars_found == []


def test_tokens():
    assert (
        ai_metadata_generator.estimate_tokens("abcd" * EXPECTED_TOKEN_10)
        == EXPECTED_TOKEN_10
    )
    assert ai_metadata_generator.estimate_tokens("a" * 100) == EXPECTED_TOKEN_25
    assert ai_metadata_generator.estimate_tokens("") == 0


def test_code_prioritizes_init(tmp_path):
    instr_dir = tmp_path / "instr"
    instr_dir.mkdir()
    (instr_dir / "__init__.py").write_text("print('hello')\n")
    (instr_dir / "foo.py").write_text("print('foo')\n")

    code = ai_metadata_generator.get_instrumentation_code(str(instr_dir))
    assert "# Source: __init__.py" in code
    assert "hello" in code
    assert "foo" in code


def test_code_empty_dir(tmp_path):
    instr_dir = tmp_path / "instr"
    instr_dir.mkdir()

    code = ai_metadata_generator.get_instrumentation_code(str(instr_dir))
    assert code.startswith("Could not find any .py files in")


def test_yaml_write(tmp_path):
    yaml_content = textwrap.dedent("""
    name: test
    instrumentation_name: test
    settings:
      - property: otel.test.enabled
        env: OTEL_TEST_ENABLED
        description: test
        default: 'true'
        type: boolean
        category: instrumentation
    """)

    instr_dir = tmp_path / "instr"
    instr_dir.mkdir()
    yamls_dir = tmp_path / "yamls"

    ai_metadata_generator.save_yaml(yaml_content, str(instr_dir), str(yamls_dir))

    out_file = yamls_dir / "instr.yaml"
    content = out_file.read_text()
    assert "OTEL_TEST_ENABLED" in content
