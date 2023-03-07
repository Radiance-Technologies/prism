"""
Mine repair instances by looping over existing project build cache.
"""
import logging
import os
import sqlite3
import traceback
from pathlib import Path
from types import TracebackType
from typing import Callable, Dict, List, Optional, Tuple, Type, Union, cast

from tqdm import tqdm
from tqdm.contrib.concurrent import process_map

from prism.data.build_cache import (
    CacheObjectStatus,
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheProtocol,
    CoqProjectBuildCacheServer,
    ProjectCommitData,
)
from prism.data.commit_map import Except
from prism.data.repair.instance import (
    ChangeSelection,
    ChangeSetMiner,
    ProjectCommitDataDiff,
    ProjectCommitDataErrorInstance,
    ProjectCommitDataRepairInstance,
    default_align,
)
from prism.util.io import atomic_write
from prism.util.radpytools.multiprocessing import synchronizedmethod

BuildRepairInstanceOutput = Union[List[ProjectCommitDataRepairInstance], Except]
"""
Type hint for the output of build_repair_instance_star.
"""
RepairMiner = Callable[[ProjectCommitDataErrorInstance,
                        ProjectCommitData],
                       List[ProjectCommitDataRepairInstance]]
"""
Signature of the function used to create repair instances.
"""
ProjectCommitHashMap = Optional[Dict[str, Optional[List[str]]]]
PreparePairsFunction = Callable[
    [CoqProjectBuildCacheServer,
     Path,
     str,
     ProjectCommitHashMap],
    List[Tuple[CacheObjectStatus,
               CacheObjectStatus]]]
"""
Signature of the function used to prepare cache item label pairs for
repair instance mining.
"""
CacheLabel = Dict[str, str]
"""
Dictionary labeling a cache object (project name, commit sha,
coq version).
"""
AugmentedErrorInstance = Tuple[ProjectCommitDataErrorInstance,
                               ProjectCommitData,
                               ChangeSelection]
"""
A tuple containing an error instance, with the repaired state used to
produce it, and the corresponding change selection.
"""


class RepairInstanceDB:
    """
    Database for storing information about saved repair instances.

    This is a single-table database. Each row in the table maps a set of
    identifying details of a repair instance to the filename that stores
    the serialized, saved repair instance.
    """

    _sql_create_records_table = """CREATE TABLE IF NOT EXISTS records (
                                       id integer PRIMARY KEY autoincrement,
                                       project_name text NOT NULL,
                                       commit_sha text NOT NULL,
                                       coq_version text NOT NULL,
                                       added_commands text,
                                       affected_commands text,
                                       changed_commands text,
                                       dropped_commands text,
                                       file_name text NOT NULL
                                   ); """
    _sql_insert_record = """INSERT INTO records (
                                project_name,
                                commit_sha,
                                coq_version,
                                added_commands,
                                affected_commands,
                                changed_commands,
                                dropped_commands,
                                file_name)
                            VALUES(
                                :project_name,
                                :commit_sha,
                                :coq_version,
                                :added_commands,
                                :affected_commands,
                                :changed_commands,
                                :dropped_commands,
                                :file_name);"""
    _sql_update_file_name = """UPDATE records
                                   SET file_name = :file_name
                                   WHERE id = :row_id;"""
    _sql_get_record = """SELECT *
                         FROM records
                         WHERE
                             project_name = :project_name
                             AND commit_sha = :commit_sha
                             AND coq_version = :coq_version
                             AND added_commands = :added_commands
                             AND affected_commands = :affected_commands
                             AND changed_commands = :changed_commands
                             AND dropped_commands = :dropped_commands
                         ORDER BY id;"""

    def __init__(self, db_location: Path):
        self.db_location = db_location
        self.connection = sqlite3.connect(str(self.db_location))
        self.cursor = self.connection.cursor()
        self.create_table()

    def __enter__(self) -> 'RepairInstanceDB':
        """
        Provide an entry point for the context manager.

        Returns
        -------
        RepairInstanceDB
            An instance of this class
        """
        return self

    def __exit__(
            self,
            ext_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType]):
        """
        Clean up once context manager ends.

        This method shuts the database down cleanly if there's an
        exception while it's open.

        Parameters
        ----------
        ext_type : Optional[Type[BaseException]]
            Exception type, if an exception is raised
        exc_value : Optional[BaseException]
            Exception itself, if one is raised
        traceback : Optional[TracebackType]
            Exception traceback, if an exception is raised
        """
        self.cursor.close()
        if isinstance(exc_value, Exception):
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()

    def create_table(self):
        """
        Create the one table this database requires.
        """
        self.cursor.execute(self._sql_create_records_table)
        self.connection.commit()

    @synchronizedmethod
    def insert_record(
            self,
            cache_label: CacheLabel,
            change_selection: ChangeSelection,
            repair_save_directory: Path) -> Path:
        """
        Insert a repair instance record into the database.

        Parameters
        ----------
        cache_label : CacheLabel
            The cache label portion of the record identifier
        change_selection : ChangeSelection
            The selected changes that further identify the record
        repair_save_directory : Path
            Directory to save the repairs to

        Returns
        -------
        Path
            The reserved path to the new repair instance file.
        """
        change_selection_mapping = change_selection.as_joined_dict()
        record = {
            **cache_label,
            **change_selection_mapping
        }
        record['file_name'] = "repair-n.yml"
        self.cursor.execute(self._sql_insert_record, record)
        self.connection.commit()
        recent_id = self.cursor.lastrowid
        if recent_id is None:
            raise RuntimeError(
                "No id was returned after the last record insertion.")
        # TODO: Add full path to new_file_name
        new_file_name = str(repair_save_directory / f"repair-{recent_id}.yml")
        self.cursor.execute(
            self._sql_update_file_name,
            {
                'file_name': new_file_name,
                'row_id': recent_id
            })
        self.connection.commit()
        return Path(new_file_name)

    def get_record(
            self,
            cache_label: CacheLabel,
            change_selection: ChangeSelection) -> Optional[Dict[str,
                                                                str]]:
        """
        Get a record from the records table if it exists.

        Parameters
        ----------
        cache_label : CacheLabel
            The cache label portion of the record identifier
        change_selection : ChangeSelection
            The selected changes that further identify the record

        Returns
        -------
        Optional[Dict[str, str]]
            The record as a dictionary, or None if no record was found

        Raises
        ------
        RuntimeError
            If multiple records are found for the query. This shouldn't
            be able to happen, and if it does, it indicates a bug.
        """
        change_selection_mapping = change_selection.as_joined_dict()
        record_to_get = {
            **cache_label,
            **change_selection_mapping
        }
        self.cursor.execute(self._sql_get_record, record_to_get)
        records = self.cursor.fetchall()
        if not records:
            return
        if len(records) > 1:
            raise RuntimeError("There are duplicate rows in the records table.")
        record = records[0]
        return {
            'id': record[0],
            'project_name': record[1],
            'commit_sha': record[2],
            'coq_version': record[3],
            'added_commands': record[4],
            'affected_commands': record[5],
            'changed_commands': record[6],
            'dropped_commands': record[7],
            'file_name': record[8]
        }


class RepairMiningExceptionLogger:
    """
    Logger for writing exception logs during repair mining process.
    """

    def __init__(self, repair_save_directory: Path):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.handler = logging.FileHandler(
            str(repair_save_directory / "repair_mining_error_log.txt"))
        self.handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.handler.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

    @synchronizedmethod
    def write_exception_log(self, exception: Except):
        """
        Write a log entry for the given exception.

        logging.Logger objects are not multi-processing-safe, so this
        method is synchronized to prevent simultaneous write attempts.

        Parameters
        ----------
        exception : Except
            Exception to write a log entry for
        """
        self.logger.exception(exception.exception)
        self.logger.error(f"Traceback: {exception.trace}")
        if exception.value is not None:
            self.logger.error(f"Preempted result: {exception.value}")


def build_repair_instance(
        error_instance: ProjectCommitDataErrorInstance,
        repaired_state: ProjectCommitData,
        change_selection: ChangeSelection,
        repair_save_directory: Path,
        repair_instance_db: RepairInstanceDB,
        miner: RepairMiner,
        exception_logger: RepairMiningExceptionLogger
) -> BuildRepairInstanceOutput:
    """
    Construct build repair instance from pairs of cache items.

    Parameters
    ----------
    error_instance : ProjectCommitDataErrorInstance
        A preconstructed example of an error.
    repaired_state : ProjectCommitData
        A state based on that of `error_instance` that is presumed to be
        repaired.
    change_selection : ChangeSelection
        The change selection that gives rise to this error instance and
        repaired state
    repair_save_directory : Path
        Path to directory to save repair instances
    repair_instance_db : RepairInstanceDB
        Database for recording new repair instances saved to disk
    miner : RepairMiner
        Function used to mine repair instances
    exception_logger : RepairMiningExceptionLogger
        Object used to log errors during repair instance building

    Returns
    -------
    BuildRepairInstanceOutput
        If a repair instance is successfully created, return that.
        If the instance is empty, return None.
    """
    try:
        result = miner(error_instance, repaired_state)
    except Exception as e:
        result = Except(None, e, traceback.format_exc())
    finally:
        write_repair_instance(
            result,
            change_selection,
            repair_save_directory,
            repair_instance_db,
            exception_logger)
    return result


def build_repair_instance_star(args: tuple) -> BuildRepairInstanceOutput:
    """
    Split arguments and call build_repair_instance.

    Parameters
    ----------
    args : tuple
        Bundled arguments for build_repair_instance

    Returns
    -------
    BuildRepairInstanceOutput
        If a repair instances are successfully created, return those.
        If build_repair_instance raises an exception, return the
        exception annotated with its in-context traceback string.
    """
    return build_repair_instance(*args)


def build_error_instances_from_label_pair(
    label_a: CacheObjectStatus,
    label_b: CacheObjectStatus,
    cache_server: CoqProjectBuildCacheServer,
    cache_root: Path,
    cache_format_extension: str,
    changeset_miner: ChangeSetMiner,
    exception_logger: RepairMiningExceptionLogger
) -> Union[List[AugmentedErrorInstance],
           Except]:
    """
    Construct error instances from pairs of cache labels.

    This function includes loading the items from the cache
    corresponding to the labels.

    Parameters
    ----------
    label_a : CacheObjectStatus
        The label corresponding to the initial state.
    label_b : CacheObjectStatus
        The label corresponding to the repaired state.
    cache_server : CoqProjectBuildCacheServer
        The cache server to connect the cache client to.
    cache_root: Path
        The path to the cache root
    cache_format_extension: str
        The extension used by the cache files
    changeset_miner : ChangeSetMiner
        The callable used to mine ChangeSelection objects
    exception_logger : RepairMiningExceptionLogger
        The object used to log error messages encountered during mining.

    Returns
    -------
    Union[List[AugmentedErrorInstance], Except]
        A list of augmented error instances if successful or an Except
        object if there's an error.
    """
    try:
        cache_client = cast(
            CoqProjectBuildCacheProtocol,
            CoqProjectBuildCacheClient(
                cache_server,
                cache_root,
                cache_format_extension))
        initial_state = cache_client.get(
            label_a.project,
            label_a.commit_hash,
            label_a.coq_version)
        repaired_state = cache_client.get(
            label_b.project,
            label_b.commit_hash,
            label_b.coq_version)
        initial_state.sort_commands()
        commit_diff = ProjectCommitDataDiff.from_commit_data(
            initial_state,
            repaired_state,
            default_align)
        error_instances: List[AugmentedErrorInstance] = []
        for changeset in changeset_miner(initial_state, commit_diff):
            error_instance = ProjectCommitDataErrorInstance.make_error_instance(
                initial_state,
                repaired_state,
                commit_diff,
                changeset,
                ProjectCommitDataErrorInstance.default_get_error_tags)
            error_instances.append((error_instance, repaired_state, changeset))
        result = error_instances
    except Exception as e:
        result = Except(None, e, traceback.format_exc())
        exception_logger.write_exception_log(result)
    return result


def build_error_instances_from_label_pair_star(
        args: tuple) -> List[ProjectCommitDataErrorInstance]:
    """
    Split arguments and call build_error_instances_from_label_pair.

    Parameters
    ----------
    args : tuple
        Bundled arguments for build_error_instances_from_label_pair.

    Returns
    -------
    List[ProjectCommitDataErrorInstance]
        A list of augmented error instances if successful or an Except
        object if there's an error.
    """
    return build_error_instances_from_label_pair(*args)


def write_repair_instance(
        potential_diff: BuildRepairInstanceOutput,
        change_selection: ChangeSelection,
        repair_file_directory: Path,
        repair_instance_db: RepairInstanceDB,
        exception_logger: RepairMiningExceptionLogger):
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
    repair_instance_db : RepairInstanceDB
        Database for recording new repair instances saved to disk
    exception_logger : RepairMiningExceptionLogger
        Object used to log errors

    Raises
    ------
    TypeError
        If potential_diff is neither of ProjectCommitDataRepairInstance
        nor of Except.
    """
    if isinstance(potential_diff, ProjectCommitDataRepairInstance):
        metadata = potential_diff.error.initial_state.project_state.project_metadata
        cache_label = {
            "project_name": metadata.project_name,
            "commit_sha": metadata.commit_sha,
            "coq_version": metadata.coq_version
        }
        file_path = repair_instance_db.insert_record(
            cache_label,
            change_selection,
            repair_file_directory)
        atomic_write(file_path, potential_diff.compress())
    elif isinstance(potential_diff, Except):
        exception_logger.write_exception_log(potential_diff)
    else:
        raise TypeError(
            f"Type {type(potential_diff)} is not recognized and can't be "
            "written.")


def prepare_label_pairs(
    cache_server: CoqProjectBuildCacheServer,
    cache_root: Path,
    cache_format_extension: str,
    project_commit_hash_map: Optional[Dict[str,
                                           Optional[List[str]]]] = None
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
    project_commit_hash_map : Dict[str, List[str] or None] or None
        An optional list of maps from project names to commit hashes.
        If this arg is None, consider all projects and commit hashes
        found in the cache.
        If this arg is not None, consider only projects found in the
        keys of the map.
        For a given project name key, if the value is None, consider all
        commit hashes for that project.
        If instead the value is a list, use only those commit hashes
        listed for that project

    Returns
    -------
    List[Tuple[CacheObjectStatus, CacheObjectStatus]]
        List of cache label pairs to be used for repair mining
    """

    def _append_if_labels_differ(
            cache_item_a: CacheObjectStatus,
            cache_item_b: CacheObjectStatus,
            cache_item_pairs: List[Tuple[CacheObjectStatus,
                                         CacheObjectStatus]]):
        """
        Check if labels differ; if so, add to list in-place.
        """
        if cache_item_a != cache_item_b:
            cache_item_pairs.append((cache_item_a, cache_item_b))

    def _loop_over_second_label(
            cache_item_a: CacheObjectStatus,
            cache_items: List[CacheObjectStatus],
            project_commit_hash_map: ProjectCommitHashMap,
            cache_item_pairs: List[Tuple[CacheObjectStatus,
                                         CacheObjectStatus]]):
        """
        Loop over the second item in the label pairs, populate list.

        Modifies cache_item_pairs in-place.
        """
        for cache_item_b in cache_items:
            if (project_commit_hash_map is None or cache_item_b.commit_hash
                    in project_commit_hash_map[project]):
                _append_if_labels_differ(
                    cache_item_a,
                    cache_item_b,
                    cache_item_pairs)

    def _loop_over_labels(
            cache_items: List[CacheObjectStatus],
            project_commit_hash_map: ProjectCommitHashMap,
            cache_item_pairs: List[Tuple[CacheObjectStatus,
                                         CacheObjectStatus]]):
        """
        Loop over all label pairs and populate cache_item_pairs.

        Modifies cache_item_pairs in-place.
        """
        for cache_item_a in cache_items:
            if (project_commit_hash_map is None or cache_item_a.commit_hash
                    in project_commit_hash_map[project]):
                _loop_over_second_label(
                    cache_item_a,
                    cache_items,
                    project_commit_hash_map,
                    cache_item_pairs)

    cache_args = (cache_server, cache_root, cache_format_extension)
    local_cache_client = cast(
        CoqProjectBuildCacheProtocol,
        CoqProjectBuildCacheClient(*cache_args))
    project_list = local_cache_client.list_projects()
    if project_commit_hash_map is not None:
        project_list = [p for p in project_list if p in project_commit_hash_map]
    all_cache_items = local_cache_client.list_status_success_only()
    cache_item_pairs: List[Tuple[CacheObjectStatus, CacheObjectStatus]] = []
    for project in project_list:
        cache_items = [t for t in all_cache_items if t.project == project]
        _loop_over_labels(
            cache_items,
            project_commit_hash_map,
            cache_item_pairs)
    return cache_item_pairs


def repair_mining_loop(
        cache_root: Path,
        repair_save_directory: Path,
        cache_format_extension: str = "yml",
        prepare_pairs: Optional[PreparePairsFunction] = None,
        repair_miner: Optional[RepairMiner] = None,
        changeset_miner: Optional[ChangeSetMiner] = None,
        serial: bool = False,
        max_workers: Optional[int] = None,
        chunk_size: int = 1,
        project_commit_hash_map: Optional[Dict[str,
                                               Optional[List[str]]]] = None):
    """
    Mine repair instances from the given build cache.

    Parameters
    ----------
    cache_root : Path
        Path to cache root to mine repair instances from
    repair_save_directory : Path
        Path to directory for saving repair instances
    cache_format_extension : str, optional
        Extension of cache files, by default "yml"
    prepare_pairs : PreparePairsFunction, optional
        Function to prepare pairs of cache item labels to be used for
        repair instance mining, by default None
    repair_miner : RepairMiner, optional
        Function to mine repair instances given an error instance and a
        repaired state, by default None
    changest_miner : Optional[ChangeSetMiner], optional
        Function to mine ChangeSelection objects, by default None
    serial : bool, optional
        Flag to control parallel execution, by default False. If True,
        use serial execution. If False, use parallel execution.
    max_workers : int or None, optional
        Maximum number of parallel workers to allow, by default None,
        which sets the value to min(32, number of cpus + 4)
    chunk_size : int, optional
        Size of job chunk sent to each worker, by default 1
    project_commit_hash_map : Dict[str, List[str] or None] or None
        An optional list of maps from project names to commit hashes.
        If this arg is None, consider all projects and commit hashes
        found in the cache.
        If this arg is not None, consider only projects found in the
        keys of the map.
        For a given project name key, if the value is None, consider all
        commit hashes for that project.
        If instead the value is a list, use only those commit hashes
        listed for that project
    """
    os.makedirs(str(repair_save_directory), exist_ok=True)
    if prepare_pairs is None:
        prepare_pairs = prepare_label_pairs
    if repair_miner is None:
        repair_miner = ProjectCommitDataRepairInstance.make_repair_instance
    if changeset_miner is None:
        changeset_miner = ProjectCommitDataErrorInstance.default_changeset_miner
    exception_logger = RepairMiningExceptionLogger(repair_save_directory)
    with CoqProjectBuildCacheServer() as cache_server:
        db_file = repair_save_directory / "repair_records.sqlite3"
        with RepairInstanceDB(db_file) as db_instance:
            cache_args = (cache_server, cache_root, cache_format_extension)
            cache_label_pairs = prepare_pairs(
                *cache_args,
                project_commit_hash_map)
            # ##########################################################
            # Build error instances
            # ##########################################################
            if serial:  # Serial
                error_instances: List[ProjectCommitDataErrorInstance] = []
                for label_a, label_b in tqdm(
                        cache_label_pairs, desc="Error instance mining"):
                    new_error_instances = build_error_instances_from_label_pair(
                        label_a,
                        label_b,
                        cache_server,
                        cache_root,
                        cache_format_extension,
                        changeset_miner,
                        exception_logger)
                    if not isinstance(new_error_instances, Except):
                        error_instances.extend(new_error_instances)
            else:  # Parallel
                # Prepare process_map kwargs:
                process_map_kwargs = {}
                if max_workers is not None:
                    process_map_kwargs["max_workers"] = max_workers
                process_map_kwargs["chunksize"] = chunk_size
                error_instance_jobs = [
                    (
                        label_a,
                        label_b,
                        cache_server,
                        cache_root,
                        cache_format_extension,
                        changeset_miner,
                        exception_logger) for label_a,
                    label_b in cache_label_pairs
                ]
                error_instances_list = process_map(
                    build_error_instances_from_label_pair_star,
                    error_instance_jobs,
                    desc="Error instance mining",
                    **process_map_kwargs)
                error_instances: List[AugmentedErrorInstance] = []
                for item in error_instances_list:
                    if not isinstance(item, Except):
                        error_instances.extend(item)
            # ##########################################################
            # Build repair instances
            # ##########################################################
            if serial:  # Serial
                for error_instance, repaired_state, change_selection in tqdm(
                        error_instances, desc="Repair instance mining."):
                    result = build_repair_instance(
                        error_instance,
                        repaired_state,
                        change_selection,
                        repair_save_directory,
                        db_instance,
                        repair_miner,
                        exception_logger)
                    if isinstance(result, Except):
                        print(result.trace)
                        raise result.exception
            else:  # Parallel
                repair_instance_jobs = [
                    (
                        error_instance,
                        repaired_state,
                        change_selection,
                        repair_save_directory,
                        db_instance,
                        repair_miner,
                        exception_logger) for error_instance,
                    repaired_state in error_instances
                ]
                process_map(
                    build_repair_instance_star,
                    repair_instance_jobs,
                    desc="Repair Mining",
                    **process_map_kwargs)
