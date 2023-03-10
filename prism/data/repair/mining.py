"""
Mine repair instances by looping over existing project build cache.
"""
import logging
import os
import sqlite3
import traceback
from multiprocessing.managers import BaseManager
from pathlib import Path
from tempfile import TemporaryDirectory
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
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
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
PreparePairsReturn = List[Tuple[CacheObjectStatus, CacheObjectStatus]]
# yapf: disable
PreparePairsFunction = Callable[[CoqProjectBuildCacheServer,
                                 Path,
                                 str,
                                 MetadataStorage,
                                 ProjectCommitHashMap],
                                PreparePairsReturn]
# yapf: enable
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

    _sql_create_records_table = """
        CREATE TABLE IF NOT EXISTS records (
            id integer PRIMARY KEY autoincrement,
            project_name text NOT NULL,
            initial_commit_sha text NOT NULL,
            repaired_commit_sha text NOT NULL,
            initial_coq_version text NOT NULL,
            repaired_coq_version text NOT NULL,
            added_commands text,
            affected_commands text,
            changed_commands text,
            dropped_commands text,
            file_name text NOT NULL
        );"""
    _sql_insert_record = """
        INSERT INTO records (
            project_name,
            initial_commit_sha,
            repaired_commit_sha,
            initial_coq_version,
            repaired_coq_version,
            added_commands,
            affected_commands,
            changed_commands,
            dropped_commands,
            file_name)
        VALUES(
            :project_name,
            :initial_commit_sha,
            :repaired_commit_sha,
            :initial_coq_version,
            :repaired_coq_version,
            :added_commands,
            :affected_commands,
            :changed_commands,
            :dropped_commands,
            :file_name);"""
    _sql_update_file_name = """
        UPDATE records
            SET file_name = :file_name
            WHERE id = :row_id;"""
    _sql_get_record = """
        SELECT *
        FROM records
        WHERE
            project_name = :project_name
            AND initial_commit_sha = :initial_commit_sha
            AND repaired_commit_sha = :repaired_commit_sha
            AND initial_coq_version = :initial_coq_version
            AND repaired_coq_version = :repaired_coq_version
            AND added_commands = :added_commands
            AND affected_commands = :affected_commands
            AND changed_commands = :changed_commands
            AND dropped_commands = :dropped_commands
        ORDER BY id;"""
    _sql_get_records_for_commit_pair = """
        SELECT *
        FROM records
        WHERE
            project_name = :project_name
            AND initial_commit_sha = :initial_commit_sha
            AND repaired_commit_sha = :repaired_commit_sha
            AND initial_coq_version = :initial_coq_version
            AND repaired_coq_version = :repaired_coq_version
        ORDER BY id;"""
    _sql_get_record_for_filename = """
        SELECT *
        FROM records
        WHERE
            file_name = :file_name
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

    @staticmethod
    def _record_to_dictionary(
        record: Tuple[int,
                      str,
                      str,
                      str,
                      str,
                      str,
                      str,
                      str,
                      str,
                      str,
                      str]
    ) -> Dict[str,
              Union[int,
                    str]]:
        return {
            'id': record[0],
            'project_name': record[1],
            'initial_commit_sha': record[2],
            'repaired_commit_sha': record[3],
            'initial_coq_version': record[4],
            'repaired_coq_version': record[5],
            'added_commands': record[6],
            'affected_commands': record[7],
            'changed_commands': record[8],
            'dropped_commands': record[9],
            'file_name': record[10]
        }

    def create_table(self):
        """
        Create the one table this database requires.
        """
        self.cursor.execute(self._sql_create_records_table)
        self.connection.commit()

    def insert_record_get_path(
            self,
            project_name: str,
            initial_commit_sha: str,
            repaired_commit_sha: str,
            initial_coq_version: str,
            repaired_coq_version: str,
            change_selection: ChangeSelection,
            repair_save_directory: Path) -> Path:
        """
        Insert a repair instance record into the database.

        Parameters
        ----------
        project_name : str
        initial_commit_sha : str
        repaired_commit_sha : str
        initial_coq_version : str
        repaired_coq_version : str
        change_selection : ChangeSelection
            The selected changes that further identify the record
        repair_save_directory : Path
            Directory to save the repairs to

        Returns
        -------
        Path
            The reserved path to the new repair instance file.

        Notes
        -----
        Summary:
        * Insert a record with a place-holder file name.
        * Immediately fetch the new row back with its auto-incremented
          row id.
        * Fetch all rows matching the project name and commit pair and
          coq verison pair.
        * Get the row indices from each returned row, sort them, and
          get the index of the just-inserted row in that list.
        * Use this index to name the file, along with the project name,
          commit sha pair, and coq version pair
        * Update the row with the newly-computed file name.
        * Return the new file name.
        """
        cache_id_label = {
            "project_name": project_name,
            "initial_commit_sha": initial_commit_sha,
            "repaired_commit_sha": repaired_commit_sha,
            "initial_coq_version": initial_coq_version,
            "repaired_coq_version": repaired_coq_version
        }
        record = {
            **cache_id_label,
            **change_selection.as_joined_dict()
        }
        record['file_name'] = "repair-n.yml"
        self.cursor.execute(self._sql_insert_record, record)
        self.connection.commit()
        inserted_row = self.get_record(
            project_name,
            initial_commit_sha,
            repaired_commit_sha,
            initial_coq_version,
            repaired_coq_version,
            change_selection)
        if inserted_row is None:
            raise RuntimeError(
                "No id was returned after the last record insertion.")
        recent_id = inserted_row["id"]
        self.cursor.execute(
            self._sql_get_records_for_commit_pair,
            cache_id_label)
        label_related_rows = self.cursor.fetchall()
        row_ids = sorted([row[0] for row in label_related_rows])
        file_index = row_ids.index(recent_id)
        new_file_name = str(
            repair_save_directory / (
                "-".join(
                    [
                        "repair",
                        project_name,
                        initial_commit_sha,
                        repaired_commit_sha,
                        initial_coq_version,
                        repaired_coq_version,
                        str(file_index)
                    ]) + ".yml"))
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
        project_name: str,
        initial_commit_sha: str,
        repaired_commit_sha: str,
        initial_coq_version: str,
        repaired_coq_version: str,
        change_selection: ChangeSelection) -> Optional[Dict[str,
                                                            Union[int,
                                                                  str]]]:
        """
        Get a record from the records table if it exists.

        Parameters
        ----------
        project_name : str
        initial_commit_sha : str
        repaired_commit_sha : str
        initial_coq_version : str
        repaired_coq_version : str
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
        record_to_get = {
            "project_name": project_name,
            "initial_commit_sha": initial_commit_sha,
            "repaired_commit_sha": repaired_commit_sha,
            "initial_coq_version": initial_coq_version,
            "repaired_coq_version": repaired_coq_version,
            **change_selection.as_joined_dict()
        }
        self.cursor.execute(self._sql_get_record, record_to_get)
        records = self.cursor.fetchall()
        if not records:
            return
        if len(records) > 1:
            raise RuntimeError("There are duplicate rows in the records table.")
        record = records[0]
        return self._record_to_dictionary(record)

    def get_record_from_file_name(self,
                                  file_name: str) -> Optional[Dict[str,
                                                                   Union[int,
                                                                         str]]]:
        """
        Get a record from the records table for a particular file name.

        Parameters
        ----------
        file_name : str
            The file name to select the record for.

        Returns
        -------
        Optional[Dict[str, Union[int, str]]]
            The selected record, if it exists. None if not.

        Raises
        ------
        RuntimeError
            If there is more than one record in the table for the given
            file name.
        """
        self.cursor.execute(
            self._sql_get_record_for_filename,
            {"file_name": file_name})
        records = self.cursor.fetchall()
        if not records:
            return
        if len(records) > 1:
            raise RuntimeError(
                f"There is more than 1 row for file {file_name}.")
        return self._record_to_dictionary(records[0])


class RepairMiningExceptionLogger:
    """
    Logger for writing exception logs during repair mining process.
    """

    def __init__(self, repair_save_directory: Path, level: int):
        self.logger = logging.getLogger(__name__)
        # Get rid of the stdout handler
        for handler in self.logger.handlers:
            self.logger.removeHandler(handler)
        self.logger.setLevel(level)
        self.handler = logging.FileHandler(
            str(repair_save_directory / "repair_mining_error_log.txt"))
        self.handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.handler.setLevel(level)
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

    @synchronizedmethod
    def write_debug_log(self, message: str):
        """
        Write a debug message.

        Parameters
        ----------
        message : str
            Message to write as a debug message to the logger.
        """
        self.logger.debug(message)


class RepairMiningExceptionLoggerServer(BaseManager):
    """
    A BaseManager-derived server for managing exception logging.
    """


RepairMiningExceptionLoggerServer.register(
    "RepairMiningExceptionLogger",
    RepairMiningExceptionLogger)


def RepairMiningExceptionLoggerClient(
        server: RepairMiningExceptionLoggerServer,
        *args,
        **kwargs) -> RepairMiningExceptionLogger:
    """
    Return client object for writing build cache.
    """
    return cast(
        RepairMiningExceptionLogger,
        server.RepairMiningExceptionLogger(*args,
                                           **kwargs))


def build_repair_instance(
        error_instance: ProjectCommitDataErrorInstance,
        repaired_state: ProjectCommitData,
        change_selection: ChangeSelection,
        repair_save_directory: Path,
        repair_instance_db_file: Path,
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
    repair_instance_db_file : Path
        Path to database for recording new repair instances saved to
        disk
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
        with RepairInstanceDB(repair_instance_db_file) as db_instance:
            initial_metadata = \
                error_instance.initial_state.project_state.project_metadata
            repaired_metadata = repaired_state.project_metadata
            if db_instance.get_record(initial_metadata.project_name,
                                      initial_metadata.commit_sha,
                                      repaired_metadata.commit_sha,
                                      initial_metadata.coq_version,
                                      repaired_metadata.coq_version,
                                      change_selection) is None:
                result = miner(error_instance, repaired_state)
            else:
                result = None
    except Exception as e:
        result = Except(None, e, traceback.format_exc())
    finally:
        if result is not None:
            write_repair_instance(
                result,
                change_selection,
                repair_save_directory,
                repair_instance_db_file,
                exception_logger,
                repaired_state.project_metadata)
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
    cache: CoqProjectBuildCacheProtocol,
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
    cache : CoqProjectBuildCacheProtocol
        The Coq project build cache object to load from
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
        initial_state = cache.get(
            label_a.project,
            label_a.commit_hash,
            label_a.coq_version)
        exception_logger.write_debug_log(
            "build_error_instances_from_label_pair: Finished loading cache for"
            f" label a: {label_a}.")
        repaired_state = cache.get(
            label_b.project,
            label_b.commit_hash,
            label_b.coq_version)
        exception_logger.write_debug_log(
            "build_error_instances_from_label_pair: Finished loading cache for"
            f" label b: {label_b}.")
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
        repair_instance_db_file: Path,
        exception_logger: RepairMiningExceptionLogger,
        repaired_state_metadata: ProjectMetadata):
    """
    Write a repair instance to disk, or log an exception.

    ProjectCommitDataDiff is serialized and written to disk. None is
    ignored. Exception is logged.

    Parameters
    ----------
    potential_diff : BuildRepairInstanceOutput
        A potential repair instance
    change_selection : ChangeSelection
        Change selection that corresponds to this repair instance
    repair_file_directory : Path
        Path to directory to store serialized repair instances
    repair_instance_db_file : Path
        Path to database for recording new repair instances saved to
        disk
    exception_logger : RepairMiningExceptionLogger
        Object used to log errors
    repaired_state_metadata : ProjectMetadata
        Metadata for the repaired state, used to determine the
        information to record for this instance.

    Raises
    ------
    TypeError
        If potential_diff is neither of ProjectCommitDataRepairInstance
        nor of Except.
    """
    if isinstance(potential_diff, ProjectCommitDataRepairInstance):
        with RepairInstanceDB(repair_instance_db_file) as repair_instance_db:
            initial_metadata = \
                potential_diff.error.initial_state.project_state.project_metadata
            file_path = repair_instance_db.insert_record_get_path(
                initial_metadata.project_name,
                initial_metadata.commit_sha,
                repaired_state_metadata.commit_sha,
                initial_metadata.coq_version,
                repaired_state_metadata.coq_version,
                change_selection,
                repair_file_directory)
            atomic_write(file_path, potential_diff.compress())
    elif isinstance(potential_diff, Except):
        exception_logger.write_exception_log(potential_diff)
    else:
        raise TypeError(
            f"Type {type(potential_diff)} is not recognized and can't be "
            "written.")


def _get_consecutive_commit_hashes(
        metadata_storage: MetadataStorage,
        project: str,
        repo_root: Path,
        cache_items: List[CacheObjectStatus]) -> List[Tuple[str,
                                                            str]]:
    """
    Build a list of consecutive commit hash tuples for project & cache.
    """
    repo = ProjectRepo(repo_root / project, metadata_storage=metadata_storage)
    commit_hashes = set(ci.commit_hash for ci in cache_items)
    dated_commit_hashes = sorted(
        [(repo.commit(ch).authored_datetime,
          ch) for ch in commit_hashes])
    return [
        (dch1[1],
         dch2[1]) for dch1,
        dch2 in zip(dated_commit_hashes,
                    dated_commit_hashes[1 :])
    ]


def prepare_label_pairs(
    cache_server: CoqProjectBuildCacheServer,
    cache_root: Path,
    cache_format_extension: str,
    metadata_storage: MetadataStorage,
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
                                         CacheObjectStatus]],
            consecutive_commit_hashes: List[Tuple[str,
                                                  str]]):
        """
        Check if labels differ; if so, add to list in-place.
        """
        if cache_item_a != cache_item_b and (
                cache_item_a.commit_hash,
                cache_item_b.commit_hash) in consecutive_commit_hashes:
            cache_item_pairs.append((cache_item_a, cache_item_b))

    def _loop_over_second_label(
            cache_item_a: CacheObjectStatus,
            cache_items: List[CacheObjectStatus],
            project_commit_hash_map: ProjectCommitHashMap,
            cache_item_pairs: List[Tuple[CacheObjectStatus,
                                         CacheObjectStatus]],
            consecutive_commit_hashes: List[Tuple[str,
                                                  str]]):
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
                    cache_item_pairs,
                    consecutive_commit_hashes)

    def _loop_over_labels(
            cache_items: List[CacheObjectStatus],
            project_commit_hash_map: ProjectCommitHashMap,
            cache_item_pairs: List[Tuple[CacheObjectStatus,
                                         CacheObjectStatus]],
            consecutive_commit_hashes: List[Tuple[str,
                                                  str]]):
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
                    cache_item_pairs,
                    consecutive_commit_hashes)

    with TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        cache_args = (cache_server, cache_root, cache_format_extension)
        local_cache_client = cast(
            CoqProjectBuildCacheProtocol,
            CoqProjectBuildCacheClient(*cache_args))
        project_list = local_cache_client.list_projects()
        if project_commit_hash_map is not None:
            project_list = [
                p for p in project_list if p in project_commit_hash_map
            ]
        all_cache_items = local_cache_client.list_status_success_only()
        cache_item_pairs: List[Tuple[CacheObjectStatus, CacheObjectStatus]] = []
        for project in project_list:
            cache_items = [t for t in all_cache_items if t.project == project]
            consecutive_commit_hashes = _get_consecutive_commit_hashes(
                metadata_storage,
                project,
                repo_root,
                cache_items)
            _loop_over_labels(
                cache_items,
                project_commit_hash_map,
                cache_item_pairs,
                consecutive_commit_hashes)
        return cache_item_pairs


def repair_mining_loop(
        cache_root: Path,
        repair_save_directory: Path,
        metadata_storage_file: Optional[Path] = None,
        cache_format_extension: str = "yml",
        prepare_pairs: Optional[PreparePairsFunction] = None,
        repair_miner: Optional[RepairMiner] = None,
        changeset_miner: Optional[ChangeSetMiner] = None,
        serial: bool = False,
        max_workers: Optional[int] = None,
        chunk_size: int = 1,
        project_commit_hash_map: Optional[Dict[str,
                                               Optional[List[str]]]] = None,
        logging_level: int = logging.DEBUG):
    """
    Mine repair instances from the given build cache.

    Parameters
    ----------
    cache_root : Path
        Path to cache root to mine repair instances from
    repair_save_directory : Path
        Path to directory for saving repair instances
    metadata_storage_file : Path or None, optional
        Path to metadata storage file to load for commit identification
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
    logging_level : int, optional
        Logging level for the exception logger, by default DEBUG.
    """
    os.makedirs(str(repair_save_directory), exist_ok=True)
    if metadata_storage_file is None:
        metadata_storage_file = Path(
            __file__).parents[3] / "dataset/agg_coq_repos.yml"
    if prepare_pairs is None:
        prepare_pairs = prepare_label_pairs
    if repair_miner is None:
        repair_miner = ProjectCommitDataRepairInstance.make_repair_instance
    if changeset_miner is None:
        changeset_miner = ProjectCommitDataErrorInstance.default_changeset_miner
    metadata_storage = MetadataStorage.load(metadata_storage_file)
    with CoqProjectBuildCacheServer() as cache_server:
        db_file = repair_save_directory / "repair_records.sqlite3"
        with RepairMiningExceptionLoggerServer() as exception_server:
            exception_logger = RepairMiningExceptionLoggerClient(
                exception_server,
                repair_save_directory,
                logging_level)
            cache_args = (cache_server, cache_root, cache_format_extension)
            cache = cast(
                CoqProjectBuildCacheProtocol,
                CoqProjectBuildCacheClient(*cache_args))
            cache_label_pairs = prepare_pairs(
                *cache_args,
                metadata_storage,
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
                        cache,
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
                        cache,
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
                        db_file,
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
                        db_file,
                        repair_miner,
                        exception_logger) for error_instance,
                    repaired_state,
                    change_selection in error_instances
                ]
                process_map(
                    build_repair_instance_star,
                    repair_instance_jobs,
                    desc="Repair Mining",
                    **process_map_kwargs)
