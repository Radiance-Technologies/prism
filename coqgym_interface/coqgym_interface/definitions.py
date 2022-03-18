"""
Module for constants used across different datasets.
"""
import json
import os
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, TypeVar, Union

import datasets
from git.exc import InvalidGitRepositoryError

from coqgym_interface.dataset import CoqGymBaseDataset
from coqgym_interface.project import ProjectDir, ProjectRepo

COQGYM_ENV_VAR: str = "COQGYM_SHARED"
DEFAULT_METADATA_FILENAME: str = "metadata.json"


class DatasetTask(Enum):
    """
    Enumerate of different task specific datasets.

    These tasks are associated with different training objectives.
    """
    LM: str = "language-modeling"
    TRD: str = "token-replacement-detection"
    ASTM: str = "ast-modeling"


class SentenceFormat(Enum):
    """
    Enumerate of different ways coq sentences maybe be formated.

    Parameters
    ----------
    raw: str
        Original source code format where sentence may be
        multiple lines.
    coq: str
        Each sentence is formatted to be on it's own line.
    coq_gloom: str
        All sentences for a proof are on the same line, while sentences
        outside of proofs are own their own line.
    """
    raw: str = "raw"
    coq: str = "coq"
    coq_gloom: str = "coq-gloom"
