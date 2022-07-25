"""
Module for storing cache extraction functions.
"""
import os
from typing import Callable, Iterable, Optional

from tqdm.contrib.concurrent import process_map

from prism.data.dataset import CoqProjectBaseDataset
from prism.project.exception import ProjectBuildError
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamAPI


def extract_cache(
        coq_version: str,
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str) -> None:
    OpamAPI.set_switch(metadata=project.metadata)
    if commit_sha not in build_cache:
        try:
            project.build()
            # Gather a list of Coq files, see
            # test_build_cache.py
        except ProjectBuildError as pbe:
            print(pbe.args)
