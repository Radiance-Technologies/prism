"""
Module for storing cache extraction functions.
"""
from typing import Set

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectCommitData,
    VernacCommandData,
)
from prism.language.gallina.analyze import SexpInfo
from prism.language.heuristic.util import ParserUtils
from prism.project.exception import ProjectBuildError
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamAPI


def extract_cache(
        coq_version: str,
        build_cache: CoqProjectBuildCache,
        project: ProjectRepo,
        commit_sha: str) -> None:
    """
    Extract cache from project commit and insert into build_cache.
    """
    OpamAPI.set_switch(metadata=project.metadata)
    if commit_sha not in build_cache:
        try:
            project.build()
            # Gather a list of Coq files, see
            # test_build_cache.py
            command_data = {}
            for filename in project.get_file_list():
                file_commands: Set[VernacCommandData] = command_data.setdefault(
                    filename,
                    set())
                doc = project.get_file(filename)
                beg_char_idx = 0
                end_char_idx = 0
                for (sentence_idx,
                     sentence) in enumerate(project.extract_sentences(
                         doc,
                         sentence_extraction_method=project
                         .sentence_extraction_method)):
                    end_char_idx += len(sentence)
                    command_type, identifier = ParserUtils.extract_identifier(sentence)
                    file_commands.add(
                        VernacCommandData(
                            identifier,
                            command_type,
                            SexpInfo.Loc(
                                filename,
                                sentence_idx,
                                0,
                                sentence_idx,
                                0,
                                beg_char_idx,
                                end_char_idx),
                            None))
                    beg_char_idx = end_char_idx
            data = ProjectCommitData(project.metadata, command_data)
            build_cache.insert(data)
        except ProjectBuildError as pbe:
            print(pbe.args)
