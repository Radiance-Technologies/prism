#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Module providing build cache analysis tools.
"""
import argparse
from typing import Dict, Iterable, List, Tuple, Union

from pandas import DataFrame
from tqdm.contrib.concurrent import process_map

from prism.data.cache.server import (
    CoqProjectBuildCache,
    ProjectCommitData,
    ProofSentence,
)
from prism.interface.coq.goals import Goals, GoalsDiff, GoalType


def build_base_dataframe(cache_items: Iterable[ProjectCommitData]) -> DataFrame:
    """
    Build the base dataframe from which statistics are gleaned.

    Parameters
    ----------
    cache_items : Iterable[ProjectCommitData]
        An iterable of cache items to build DF from

    Returns
    -------
    DataFrame
        The resulting DF
    """
    row_dicts: List[Dict[str, Union[str, int]]] = []
    for item in cache_items:
        sorted_vernac_dict = item.sorted_sentences()
        for filename, sentence_list in sorted_vernac_dict.items():
            # Previous goal counts
            previous_goals = Goals()
            for sentence in sentence_list:
                # Goals
                previous_goals, goals_counts, goals_hypothesis_counts = \
                    process_goals(previous_goals, sentence.goals)
                proof_idx = sentence.proof_index + 1 if isinstance(
                    sentence,
                    ProofSentence) else 0
                proof_step_idx = sentence.proof_step_index if isinstance(
                    sentence,
                    ProofSentence) else 0
                row_dicts.append(
                    create_row(
                        item.project_metadata.project_name,
                        item.project_metadata.commit_sha,
                        item.project_metadata.coq_version,
                        filename,
                        sentence.command_index,
                        proof_idx,
                        proof_step_idx,
                        sentence.command_type,
                        goals_counts,
                        goals_hypothesis_counts,
                        sentence.text))
    return DataFrame(row_dicts)


def process_goals(
    previous_goals: Goals,
    current_goals: Union[Goals,
                         GoalsDiff,
                         None]
) -> Tuple[Goals,
           Dict[str,
                int],
           Dict[str,
                int]]:
    """
    Process goals for a VernacSentence.

    Accumulate GoalsDiff patches if necessary.

    Parameters
    ----------
    previous_goals : Goals
        The open Goals up to now
    current_goals : Union[Goals, GoalsDiff, None]
        The goals to be processed

    Returns
    -------
    Goals
        Open Goals after this step
    Dict[str, int]
        Goal counts per category
    Dict[str, int]
        Total hypothesis counts per goal category
    """
    if current_goals is not None:
        goals_or_goalsdiff = current_goals
    else:
        goals_or_goalsdiff = Goals()
    if isinstance(goals_or_goalsdiff, Goals):
        goals = goals_or_goalsdiff
    elif isinstance(goals_or_goalsdiff, GoalsDiff):
        goals = goals_or_goalsdiff.patch(previous_goals)
    previous_goals = goals
    goals_counts = goals.counts
    goals_hypothesis_counts = goals.hypothesis_counts
    return previous_goals, goals_counts, goals_hypothesis_counts


def create_row(
        project_name: str,
        commit_sha: str,
        coq_version: str,
        filename: str,
        command_idx: int,
        proof_index: int,
        proof_step_index: int,
        command_type: str,
        goals_counts: Dict[str,
                           int],
        goals_hypothesis_counts: Dict[str,
                                      int],
        sentence_text: str) -> Dict[str,
                                    Union[int,
                                          str]]:
    """
    Create a row dictionary using the inputs.

    Returns
    -------
    Dict[str, Union[int, str]]
        The row dictionary
    """
    return {
        "project name":
            project_name,
        "commit hash":
            commit_sha,
        "coq version":
            coq_version,
        "filename":
            filename,
        "command index":
            command_idx,
        "proof index":
            proof_index,
        "proof step index":
            proof_step_index,
        "command type":
            command_type,
        "foreground goal count":
            goals_counts[GoalType.FOREGROUND.name],
        "background goal count":
            goals_counts[GoalType.BACKGROUND.name],
        "shelved goal count":
            goals_counts[GoalType.SHELVED.name],
        "abandoned goal count":
            goals_counts[GoalType.ABANDONED.name],
        "foreground hypothesis count":
            goals_hypothesis_counts[GoalType.FOREGROUND.name],
        "background hypothesis count":
            goals_hypothesis_counts[GoalType.BACKGROUND.name],
        "shelved hypothesis count":
            goals_hypothesis_counts[GoalType.SHELVED.name],
        "abandoned hypothesis count":
            goals_hypothesis_counts[GoalType.ABANDONED.name],
        "sentence whitespace delimited token count":
            len(sentence_text.split()),
        "sentence string length":
            len(sentence_text)
    }


def cache_get_star(
        args: Tuple[CoqProjectBuildCache,
                    str,
                    str,
                    str]) -> ProjectCommitData:
    """
    Create call to and arguments for cache get operation from tuple.

    Parameters
    ----------
    args : Tuple[CoqProjectBuildCache, str, str, str]
        Cache object and args in a tuple

    Returns
    -------
    ProjectCommitData
        Fetched cache object
    """
    return args[0].get(*args[1 :])


def main(cache_root: str):
    """
    Analyze cache.
    """
    cache = CoqProjectBuildCache(cache_root)
    status_list = cache.list_status_success_only()
    inputs = [
        (cache,
         s.project,
         s.commit_hash,
         s.coq_version) for s in status_list
    ]
    cache_items = process_map(cache_get_star, inputs, desc="Cache tuple")
    df = build_base_dataframe(cache_items)
    print(df)
    df.to_csv("base_df.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-root",
        help="Root folder to use for CoqProjectBuildCache")
    args = parser.parse_args()
    cache_root: str = args.cache_root
    main(cache_root)
