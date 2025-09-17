from metadata import ai_metadata_generator
import shutil
import os

def test_repeatability_flask():
    """Runs metadata generation twice for one instrumentation and compares results.
    Treat as 'online' test."""
    # Clone the repo
    repo_url = "https://github.com/open-telemetry/opentelemetry-python-contrib.git"
    temp_dir = ai_metadata_generator.clone_repo(repo_url)
    instr_dir = os.path.join(temp_dir, "instrumentation", "opentelemetry-instrumentation-django")
    if not os.path.isdir(instr_dir):
        print("Instrumentation not found: skipping test.")
        shutil.rmtree(temp_dir)
        return

    yaml1 = ai_metadata_generator.generate_instrumentation_metadata(instr_dir)
    yaml2 = ai_metadata_generator.generate_instrumentation_metadata(instr_dir)

    assert isinstance(yaml1, str)
    assert isinstance(yaml2, str)

    if yaml1 != yaml2:
        # Print all lines that differ
        lines1 = set(yaml1.splitlines())
        lines2 = set(yaml2.splitlines())
        only_in_1 = lines1 - lines2
        only_in_2 = lines2 - lines1
        overlap = len(lines1 & lines2) / max(len(lines1), len(lines2))
        print(f"Differences detected, overlap: {overlap:.2f}")
        if only_in_1:
            print("Lines only in first YAML:")
            for line in only_in_1:
                print(line)
        if only_in_2:
            print("Lines only in second YAML:")
            for line in only_in_2:
                print(line)
        assert overlap > 0.7
    else:
        print("No differences detected.")

    # delete cloned repo after test
    shutil.rmtree(temp_dir)
