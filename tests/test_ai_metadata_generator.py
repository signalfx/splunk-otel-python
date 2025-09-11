import textwrap
import pytest
from metadata import ai_metadata_generator


def test_extract_env_vars_from_code_should_find_envs_in_code_and_comments():
    code = """
    foo = os.getenv("OTEL_FOO")
    bar = os.environ.get('SPLUNK_BAR')
    # OTEL_BAZ in a comment
    """
    vars_found = ai_metadata_generator.extract_env_vars_from_code(code)
    assert 'OTEL_FOO' in vars_found
    assert 'SPLUNK_BAR' in vars_found
    assert 'OTEL_BAZ' in vars_found
    assert len(vars_found) == 3


def test_extract_env_vars_from_code_should_return_empty_for_no_envs():
    code = "print('no envs here')"
    vars_found = ai_metadata_generator.extract_env_vars_from_code(code)
    assert vars_found == []


@pytest.mark.parametrize("text,expected", [
    ("abcd" * 10, 10),   # 40 chars → 10 tokens
    ("a" * 100, 25),     # 100 chars → 25 tokens
    ("", 0),             # empty string
])
def test_estimate_tokens(text, expected):
    assert ai_metadata_generator.estimate_tokens(text) == expected


def test_get_instrumentation_code_should_prioritize_init_file(tmp_path):
    instr_dir = tmp_path / "instr"
    instr_dir.mkdir()
    (instr_dir / "__init__.py").write_text("print('hello')\n")
    (instr_dir / "foo.py").write_text("print('foo')\n")

    code = ai_metadata_generator.get_instrumentation_code(str(instr_dir))

    assert "# Source: __init__.py" in code
    assert "hello" in code
    assert "foo" in code


def test_get_instrumentation_code_should_return_empty_for_empty_dir(tmp_path):
    instr_dir = tmp_path / "instr"
    instr_dir.mkdir()

    code = ai_metadata_generator.get_instrumentation_code(str(instr_dir))
    assert code.startswith("Could not find any .py files in")


def test_save_yaml_should_write_file(tmp_path):
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
    assert out_file.exists()

    content = out_file.read_text()
    assert "name: test" in content
    assert "OTEL_TEST_ENABLED" in content