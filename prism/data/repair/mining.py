"""
Mine repair instances by looping over existing project build cache.
"""
import traceback
from pathlib import Path
from typing import List, Optional, Tuple, Union, cast

from tqdm.contrib.concurrent import process_map

from prism.data.build_cache import (
    CacheObjectStatus,
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
)
from prism.data.repair.align import default_align
from prism.data.repair.instance import ProjectCommitDataDiff

AnnotatedException = Tuple[Exception, str]
"""
An exception bundled with its traceback captured in context.
"""
BuildRepairInstanceOutput = Optional[Union[ProjectCommitDataDiff,
                                           AnnotatedException]]
"""
Type hint for the output of build_repair_instance_star.
"""


def build_repair_instance(
        cache_args: Tuple[CoqProjectBuildCacheServer,
                          Path,
                          str],
        cache_label_a: CacheObjectStatus,
        cache_label_b: CacheObjectStatus) -> Optional[ProjectCommitDataDiff]:
    """
    Construct build repair instance from pairs of cache items.

    Parameters
    ----------
    cache_server : Tuple[CoqProjectBuildCacheServer, Path, str]
        Args to instantiate cache client
    cache_label_a : CacheObjectStatus
        The initial cache label used to form the repair instance
    cache_label_b : CacheObjectStatus
        The final cache label used to form the repair instance

    Returns
    -------
    Optional[ProjectCommitDataDiff]
        If a repair instance is successfully created, return that.
        If the instance is empty, return None.
    """
    cache_client = cast(
        CoqProjectBuildCacheProtocol,
        CoqProjectBuildCacheClient(*cache_args))
    cache_item_a = cache_client.get(
        cache_label_a.project,
        cache_label_a.commit_hash,
        cache_label_a.coq_version)
    cache_item_b = cache_client.get(
        cache_label_b.project,
        cache_label_b.commit_hash,
        cache_label_b.coq_version)
    diff = ProjectCommitDataDiff.from_commit_data(
        cache_item_a,
        cache_item_b,
        default_align)
    if diff.is_empty:
        return None
    else:
        return diff


def build_repair_instance_star(
    args: Tuple[CoqProjectBuildCacheServer,
                CacheObjectStatus,
                CacheObjectStatus]
) -> BuildRepairInstanceOutput:
    """
    Split arguments and call build_repair_instance.

    Parameters
    ----------
    args : Tuple[CoqProjectBuildCacheServer, CacheObjectStatus,
                 CacheObjectStatus]
        Bundled arguments for build_repair_instance

    Returns
    -------
    BuildRepairInstanceOutput
        If a repair instance is successfully created, return that.
        If the instance is empty, return None.
        If build_repair_instance raises an exception, return the
        exception annotated with its in-context traceback string.
    """
    result = None
    try:
        result = build_repair_instance(*args)
    except Exception as e:
        result = (e, traceback.format_exc())
    finally:
        write_repair_instance(result)
    return result


def write_repair_instance(
        potential_diff: BuildRepairInstanceOutput,
        repair_file_directory: Path):
    """
    Write a repair instance to disk, or log an exception.

    ProjectCommitDataDiff is serialized and written to disk. None is
    ignored. Exception is logged.

    Parameters
    ----------
    potential_diff : BuildRepairInstanceOutput
        A potential repair instance
    repair_file_directory : Path
        Path to directory to store serialized repair instances
    """
    ...


def repair_mining_loop(
        cache_root: Path,
        cache_format_extension: str = "yml",
        serial: bool = False):
    """
    Mine repair instances from the given build cache.

    Parameters
    ----------
    cache_root : Path
        Path to cache root to mine repair instances from
    cache_format_extension : str, optional
        Extension of cache files, by default "yml"
    serial : bool, optional
        Flag to control parallel execution, by default False. If True,
        use serial execution. If False, use parallel execution.
    """
    coq_versions = [
        "8.9.1",
        "8.10.2",
        "8.11.2",
        "8.12.2",
        "8.13.2",
        "8.14.1",
        "8.15.2"
    ]
    with CoqProjectBuildCacheServer() as cache_server:
        cache_args = (cache_server, cache_root, cache_format_extension)
        local_cache_client = cast(
            CoqProjectBuildCacheProtocol,
            CoqProjectBuildCacheClient(*cache_args))
        project_list = local_cache_client.list_projects()
        all_cache_items = local_cache_client.list_status_success_only()
        cache_item_pairs: List[Tuple[CacheObjectStatus, CacheObjectStatus]] = []
        for project in project_list:
            for coq_version in coq_versions:
                cache_items = [
                    t for t in all_cache_items
                    if t.project == project and t.coq_version == coq_version
                ]
                for cache_item_a in cache_items:
                    for cache_item_b in cache_items:
                        if cache_item_a != cache_item_b:
                            cache_item_pairs.append(
                                (cache_item_a,
                                 cache_item_b))
        jobs = [(cache_args, a, b) for a, b in cache_item_pairs]
        if serial:
            for job in jobs:
                result = build_repair_instance_star(job)
                if isinstance(result, AnnotatedException):
                    print(result[1])
                    raise result[0]
        else:
            process_map(build_repair_instance_star, jobs)
