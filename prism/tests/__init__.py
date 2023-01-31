"""
Common test utilities for the entire project.

This subpackage directory also provides a spot for external data to be
stored with a fixed-path relationship to the rest of the package.
"""

from pathlib import Path

_TEST_ROOT = Path(__file__)
_PROJECT_ROOT = _TEST_ROOT.parent
_COQ_EXAMPLES_PATH = _PROJECT_ROOT / "coq_examples"
_DATA_PATH = _PROJECT_ROOT / "data"
_SCRIPTS_PATH = _PROJECT_ROOT / "scripts"
_TIMEOUT_SCRIPT_PATH = _SCRIPTS_PATH / "timeout.py"
_MEMORY_SCRIPT_PATH = _SCRIPTS_PATH / "memory.py"

_MINIMAL_METADATA = _COQ_EXAMPLES_PATH / "minimal_metadata.yml"
_MINIMAL_METASTORAGE = _COQ_EXAMPLES_PATH / "comp_cert_storage.yml"
_PROJECT_EXAMPLES_PATH = _PROJECT_ROOT / "projects"
