import os
from copy import deepcopy
from typing import Tuple

import seutil

from prism.data.build_cache import CoqProjectBuildCache, VernacCommandData
from prism.data.repair.align import assign_commits, default_command_distance
from prism.data.repair.diff import compute_git_diff
from prism.data.repair.instance import (
    ProjectCommitData,
    ProjectCommitDataDiff,
    ProjectCommitDataErrorInstance,
    ProjectCommitDataRepairInstance,
    ProjectCommitDataState,
    ProjectCommitDataStateDiff,
    VernacCommandDataListDiff,
)


def get_cache(cache_root: str, coq_version: str) -> CoqProjectBuildCache:
    cache: CoqProjectBuildCache = CoqProjectBuildCache(cache_root)
    for item in cache.list_status_success_only():
        if item.coq_version == coq_version:
            print("Project:", item.project, "    commit:", item.commit_hash)
    return cache


def load_from_cache(
        cache: CoqProjectBuildCache,
        project: str,
        commit_sha_1: str,
        commit_sha_2: str,
        coq_version: str):
    initial_state = cache.get(project, commit_sha_1, coq_version)
    initial_state.write_coq_project("initial_state")
    repaired_state = cache.get(project, commit_sha_2, coq_version)
    repaired_state.write_coq_project("repaired_state")
    return initial_state, repaired_state


def get_repaired_state_diff(initial_state, repaired_state):
    return ProjectCommitDataDiff.from_commit_data(
        initial_state,
        repaired_state,
        lambda x,
        y: assign_commits(x,
                          y,
                          default_command_distance,
                          0.4),
        compute_git_diff(initial_state,
                         repaired_state))


def get_error_state_diff(repaired_state_diff, changed_proof_file: str):
    modified_repaired_state_diff = deepcopy(repaired_state_diff)
    changes = modified_repaired_state_diff.changes[changed_proof_file]
    cmds = changes.changed_commands  # + changes.added_commands + changes.moved_commands # + changes.dropped_commands
    changed_cmd = None
    for cmd_idx, cmd in cmds.items():
        if changed_cmd is not None:
            break
        for proof in cmd.proofs:
            changed_cmd = cmd
            break
    if changed_cmd is None:
        raise ValueError("No proof changes found")
    cmds.pop(cmd_idx)
    changed_proof_data: VernacCommandData = changed_cmd
    # remove changed proof from repaired_state_diff to yield error state
    error_state_diff: ProjectCommitDataDiff = modified_repaired_state_diff
    return changed_proof_data, error_state_diff


def get_error_state(initial_state, error_state_diff):
    error_state = error_state_diff.patch(initial_state)
    error_state.write_coq_project("error_state")
    return error_state


def rebase_repaired_on_error(error_state, repaired_state):
    # rebase repaired_state_diff on error state
    return ProjectCommitDataDiff.from_commit_data(
        error_state,
        repaired_state,
        lambda x,
        y: assign_commits(x,
                          y,
                          default_command_distance,
                          0.4),
        compute_git_diff(error_state,
                         repaired_state),
    )


def changed_proof_location(
        repaired_state_diff,
        error_state,
        changed_proof_file: str):
    # get location of changed proof in error state
    error_command_idx = list(
        repaired_state_diff.changes[changed_proof_file].changed_commands.keys()
    )[0]
    error_location = error_state.command_data[changed_proof_file][
        error_command_idx].location
    return error_location


def make_repair_instance(
        initial_state: ProjectCommitData,
        error_state_diff: ProjectCommitDataDiff,
        error_location,
        changed_proof_data: VernacCommandData,
        repaired_state_diff: ProjectCommitDataDiff):
    repair_instance: ProjectCommitDataRepairInstance = ProjectCommitDataRepairInstance(
        error=ProjectCommitDataErrorInstance(
            project_name=initial_state.project_metadata.project_name,
            initial_state=ProjectCommitDataState(initial_state,
                                                 None,
                                                 None),
            change=ProjectCommitDataStateDiff(error_state_diff,
                                              None),
            error_location=error_location,
            tags={changed_proof_data.command_type}),
        repaired_state_or_diff=ProjectCommitDataStateDiff(
            repaired_state_diff,
            None))
    compressed = repair_instance.compress()
    seutil.io.dump("repair_instance_compressed.yml", compressed)
    seutil.io.dump("repair_instance_uncompressed.yml", repair_instance)
    return repair_instance


if __name__ == "__main__":
    coq_version = "8_10_2"
    cache_root = "/shared/PEARLS/caching_2023-01-19"
    project = "hoare-tut"
    commit_sha_1 = "bda0bc601a038ba6b65da2e3c52cc02c4d910f35"
    commit_sha_2 = "269c0cabb267be44e5d85e568c11f18562add6c4"
    changed_proof_file: str = "exgcd.v"

    cache = get_cache(cache_root, coq_version)

    (initial_state,
     repaired_state) = load_from_cache(
         cache,
         project,
         commit_sha_1,
         commit_sha_2,
         coq_version)

    repaired_state_diff = get_repaired_state_diff(initial_state, repaired_state)
    (changed_proof_data,
     error_state_diff) = get_error_state_diff(
         repaired_state_diff,
         changed_proof_file)

    error_state = get_error_state(
        initial_state,
        error_state_diff,
    )

    repaired_state_diff = rebase_repaired_on_error(error_state, repaired_state)

    error_location = changed_proof_location(
        repaired_state_diff,
        error_state,
        changed_proof_file)

    repair_instance = make_repair_instance(
        initial_state,
        error_state_diff,
        error_location,
        changed_proof_data,
        repaired_state_diff)
