"""
Mine repair instances by looping over existing project build cache.
"""
import traceback
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union, cast

from tqdm.contrib.concurrent import process_map

from prism.data.build_cache import (
    CacheObjectStatus,
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
    ProjectCommitData,
)
from prism.data.commit_map import Except
from prism.data.repair.instance import ProjectCommitDataRepairInstance

BuildRepairInstanceOutput = Optional[Union[
    List[ProjectCommitDataRepairInstance],
    Except]]
"""
Type hint for the output of build_repair_instance_star.
"""
MiningFunctionSignature = Callable[[ProjectCommitData,
                                    ProjectCommitData],
                                   List[ProjectCommitDataRepairInstance]]
"""
Signature of the worker function used in the repair mining loop.
"""
PreparePairsFunctionSignature = Callable[
    [CoqProjectBuildCacheServer,
     Path,
     str],
    List[Tuple[CacheObjectStatus,
               CacheObjectStatus]]]
"""
Signature of the function used to prepare cache item label pairs for
repair instance mining.
"""


def build_repair_instance(
    cache_args: Tuple[CoqProjectBuildCacheServer,
                      Path,
                      str],
    miner: MiningFunctionSignature,
    cache_label_a: CacheObjectStatus,
    cache_label_b: CacheObjectStatus
) -> Optional[List[ProjectCommitDataRepairInstance]]:
    """
    Construct build repair instance from pairs of cache items.

    Parameters
    ----------
    cache_server : Tuple[CoqProjectBuildCacheServer, Path, str]
        Args to instantiate cache client
    miner : MiningFunctionSignature
        Function used to mine repair instances
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
    repair_instances = miner(cache_item_a, cache_item_b)
    if repair_instances:
        return repair_instances


def build_repair_instance_star(
    args: Tuple[CoqProjectBuildCacheServer,
                MiningFunctionSignature,
                CacheObjectStatus,
                CacheObjectStatus]
) -> BuildRepairInstanceOutput:
    """
    Split arguments and call build_repair_instance.

    Parameters
    ----------
    args : Tuple[CoqProjectBuildCacheServer, MiningFunctionSignature,
                 CacheObjectStatus, CacheObjectStatus]
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
        result = Except(None, e, traceback.format_exc())
    finally:
        write_repair_instance(result)
    return result


def default_miner(
        commit_a: ProjectCommitData,
        commit_b: ProjectCommitData) -> List[ProjectCommitDataRepairInstance]:
    """
    Provide default function for mining repair instances.

    Parameters
    ----------
    commit_a : ProjectCommitData
        Initial commit to use to generate repair instance
    commit_b : ProjectCommitData
        Repaired commit to use to generate repair instance

    Returns
    -------
    List[ProjectCommitDataRepairInstance]
        List of mined repair instances
    """
    return ProjectCommitDataRepairInstance.mine_from_successful_commits(
        commit_a,
        commit_b)


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


def prepare_state_pairs(
    cache_server: CoqProjectBuildCacheServer,
    cache_root: Path,
    cache_format_extension: str
) -> List[Tuple[CacheObjectStatus,
                CacheObjectStatus]]:
    """
    Prepare pairs of cache item labels to be used for repair mining.

    Parameters
    ----------
    cache_server : CoqProjectBuildCacheServer
        Cache server
    cache_root : Path
        Root directory to load cache from
    cache_format_extension : str
        Extension format used by the cache files

    Returns
    -------
    List[Tuple[CacheObjectStatus, CacheObjectStatus]]
        List of cache label pairs to be used for repair mining
    """
    cache_args = (cache_server, cache_root, cache_format_extension)
    local_cache_client = cast(
        CoqProjectBuildCacheProtocol,
        CoqProjectBuildCacheClient(*cache_args))
    project_list = local_cache_client.list_projects()
    all_cache_items = local_cache_client.list_status_success_only()
    cache_item_pairs: List[Tuple[CacheObjectStatus, CacheObjectStatus]] = []
    for project in project_list:
        cache_items = [t for t in all_cache_items if t.project == project]
        for cache_item_a in cache_items:
            for cache_item_b in cache_items:
                if cache_item_a != cache_item_b:
                    cache_item_pairs.append((cache_item_a, cache_item_b))
    return cache_item_pairs


def repair_mining_loop(
        cache_root: Path,
        prepare_pairs: PreparePairsFunctionSignature = prepare_state_pairs,
        miner: MiningFunctionSignature = default_miner,
        cache_format_extension: str = "yml",
        serial: bool = False):
    """
    Mine repair instances from the given build cache.

    Parameters
    ----------
    cache_root : Path
        Path to cache root to mine repair instances from
    prepare_pairs : PreparePairsFunctionSignature, optional
        Function to prepare pairs of cache item labels to be used for
        repair instance mining
    miner : MiningFunctionSignature, optional
        Worker function to mine repair instances given a pair of cache
        objects
    cache_format_extension : str, optional
        Extension of cache files, by default "yml"
    serial : bool, optional
        Flag to control parallel execution, by default False. If True,
        use serial execution. If False, use parallel execution.
    """
    with CoqProjectBuildCacheServer() as cache_server:
        cache_args = (cache_server, cache_root, cache_format_extension)
        cache_item_pairs = prepare_pairs(*cache_args)
        jobs = [(cache_args, miner, a, b) for a, b in cache_item_pairs]
        if serial:
            for job in jobs:
                result = build_repair_instance_star(job)
                if isinstance(result, Except):
                    print(result[1])
                    raise result[0]
        else:
            process_map(build_repair_instance_star, jobs)
