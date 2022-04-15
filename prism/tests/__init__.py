"""
Common test utilities for the entire project.

This subpackage directory also provides a spot for external data to be
stored with a fixed-path relationship to the rest of the package.
"""

from pathlib import Path

_TEST_ROOT = Path(__file__)
_PROJECT_ROOT = _TEST_ROOT.parent
_COQ_EXAMPLES_PATH = _PROJECT_ROOT / "coq_examples"
