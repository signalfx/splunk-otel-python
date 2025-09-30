import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../metadata/generator")))
import ai_metadata_generator
import pytest

logging.basicConfig(level=logging.INFO, force=True)

# This test is marked as manual and will not run in CI by default.
# Run manually:
#     pytest -m manual -s   # show output
# To run all tests except manual ones :
#     pytest -m "not manual"

MIN_OVERLAP = 0.7


@pytest.mark.manual
def test_repeatability_flask():
    """Runs metadata generation twice for one instrumentation and compares results.
    Treat as 'online' test."""
    repo_url = "https://github.com/open-telemetry/opentelemetry-python-contrib.git"
    temp_dir = ai_metadata_generator.clone_repo(repo_url)
    instr_dir = os.path.join(temp_dir, "instrumentation", "opentelemetry-instrumentation-django")
    if not os.path.isdir(instr_dir):
        logging.warning("Instrumentation not found: skipping test.")
        shutil.rmtree(temp_dir)
        return

    yaml1 = ai_metadata_generator.generate_instrumentation_metadata(instr_dir)
    yaml2 = ai_metadata_generator.generate_instrumentation_metadata(instr_dir)

    assert isinstance(yaml1, str)
    assert isinstance(yaml2, str)

    if yaml1 != yaml2:
        # Log all lines that differ
        lines1 = set(yaml1.splitlines())
        lines2 = set(yaml2.splitlines())
        only_in_1 = lines1 - lines2
        only_in_2 = lines2 - lines1
        overlap = len(lines1 & lines2) / max(len(lines1), len(lines2))
        logging.info("Differences detected, overlap: %.2f", overlap)
        if only_in_1:
            logging.info("Lines only in first YAML:")
            for line in only_in_1:
                logging.info(line)
        if only_in_2:
            logging.info("Lines only in second YAML:")
            for line in only_in_2:
                logging.info(line)
        assert overlap > MIN_OVERLAP
    else:
        logging.info("No differences detected.")

    # delete cloned repo after test
    shutil.rmtree(temp_dir)
