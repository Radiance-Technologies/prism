"""
Mine repair instances by looping over existing project build cache.
"""
import sqlite3
import traceback
from dataclasses import asdict
from pathlib import Path
from types import TracebackType
from typing import Callable, Dict, List, Optional, Tuple, Type, Union, cast

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
    ProjectCommitDataRepairInstance,
)
from prism.util.io import atomic_write
from prism.util.radpytools.multiprocessing import synchronizedmethod

BuildRepairInstanceOutput = Union[List[ProjectCommitDataRepairInstance], Except]
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
CacheLabel = Dict[str, str]
"""
Dictionary labeling a cache object (project name, commit sha,
coq version).
"""
ChangeSelectionMapping = Dict[str, str]
"""
Dictionary mapping field names of ChangeSelection to strings derived
from those fields.
"""


class RepairInstanceDB:
    """
    Database for storing information about saved repair instances.

    This is a single-table database. Each row in the table maps a set of
    identifying details of a repair instance to the filename that stores
    the serialized, saved repair instance.
    """

    sql_create_records_table = """CREATE TABLE IF NOT EXISTS records (
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
    sql_insert_record = """INSERT INTO records (
                               project_name,
                               commit_sha,
                               coq_version,
                               added_commands,
                               affected_commands,
                               changed_commands,
                               dropped_commands,
                               file_name)
                           VALUES(
                               {project_name},
                               {commit_sha},
                               {coq_version},
                               {added_commands},
                               {affected_commands},
                               {changed_commands},
                               {dropped_commands},
                               {file_name});"""
    sql_update_file_name = """UPDATE records
                              SET file_name = {file_name}
                              WHERE id = {row_id};"""
    sql_get_record = """SELECT *
                        FROM records
                        WHERE
                            project_name = {project_name}
                            AND commit_sha = {commit_sha}
                            AND coq_version = {coq_version}
                            AND added_commands = {added_commands}
                            AND affected_commands = {affected_commands}
                            AND changed_commands = {changed_commands}
                            AND dropped_commands = {dropped_commands}
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
        self.cursor.execute(self.sql_create_records_table)
        self.connection.commit()

    @synchronizedmethod
    def insert_record(
            self,
            cache_label: CacheLabel,
            change_selection: ChangeSelection) -> Path:
        """
        Insert a repair instance record into the database.

        Parameters
        ----------
        cache_label : CacheLabel
            The cache label portion of the record identifier
        change_selection : ChangeSelection
            The selected changes that further identify the record

        Returns
        -------
        Path
            The reserved path to the new repair instance file.
        """
        change_selection_mapping = self.process_change_selection(
            change_selection)
        record = {
            **cache_label,
            **change_selection_mapping
        }
        record['file_name'] = "repair-n.yml"
        self.cursor.execute(self.sql_insert_record.format(**record))
        self.connection.commit()
        recent_id = self.cursor.lastrowid
        if recent_id is None:
            raise RuntimeError(
                "No id was returned after the last record insertion.")
        # TODO: Add full path to new_file_name
        new_file_name = f"repair-{recent_id}.yml"
        self.cursor.execute(
            self.sql_update_file_name.format(
                file_name=new_file_name,
                row_id=recent_id))
        self.connection.commit()

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
        change_selection_mapping = self.process_change_selection(
            change_selection)
        record_to_get = {
            **cache_label,
            **change_selection_mapping
        }
        self.cursor.execute(self.sql_get_record.format(**record_to_get))
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

    @staticmethod
    def process_change_selection(
            change_selection: ChangeSelection) -> ChangeSelectionMapping:
        """
        Process ChangeSelection item to sort and combine field values.

        Parameters
        ----------
        change_selection : ChangeSelection
            ChangeSelection object to process

        Returns
        -------
        ChangeSelectionMapping
            Mapping containing results
        """
        # This function could be a one-liner, but that would just be too
        # much.
        mapping = {}
        for key, value in asdict(change_selection).items():
            mapping[key] = " ".join(
                [f"{item[0]} {item[1]}" for item in sorted(value)])
        return mapping


def build_repair_instance(
        cache_args: Tuple[CoqProjectBuildCacheServer,
                          Path,
                          str],
        repair_save_directory: Path,
        repair_instance_db: RepairInstanceDB,
        miner: MiningFunctionSignature,
        cache_label_a: CacheObjectStatus,
        cache_label_b: CacheObjectStatus
) -> List[ProjectCommitDataRepairInstance]:
    """
    Construct build repair instance from pairs of cache items.

    Parameters
    ----------
    cache_server : Tuple[CoqProjectBuildCacheServer, Path, str]
        Args to instantiate cache client
    repair_save_directory : Path
        Path to directory to save repair instances
    repair_instance_db : RepairInstanceDB
        Database for recording new repair instances saved to disk
    miner : MiningFunctionSignature
        Function used to mine repair instances
    cache_label_a : CacheObjectStatus
        The initial cache label used to form the repair instance
    cache_label_b : CacheObjectStatus
        The final cache label used to form the repair instance

    Returns
    -------
    List[ProjectCommitDataRepairInstance]
        If a repair instance is successfully created, return that.
        If the instance is empty, return None.
    """
    try:
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
        result = miner(cache_item_a, cache_item_b)
    except Exception as e:
        result = Except(None, e, traceback.format_exc())
    finally:
        write_repair_instance(result, repair_save_directory, repair_instance_db)
    return result


def build_repair_instance_star(
    args: Tuple[CoqProjectBuildCacheServer,
                Path,
                str,
                Path,
                RepairInstanceDB,
                MiningFunctionSignature,
                CacheObjectStatus,
                CacheObjectStatus]
) -> BuildRepairInstanceOutput:
    """
    Split arguments and call build_repair_instance.

    Parameters
    ----------
    args : Tuple[CoqProjectBuildCacheServer, Path, str, Path,
                 RepairInstanceDB, MiningFunctionSignature,
                 CacheObjectStatus, CacheObjectStatus]
        Bundled arguments for build_repair_instance

    Returns
    -------
    BuildRepairInstanceOutput
        If a repair instances are successfully created, return those.
        If build_repair_instance raises an exception, return the
        exception annotated with its in-context traceback string.
    """
    result = build_repair_instance(*args)
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
    return ProjectCommitDataRepairInstance.mine_repair_examples(
        commit_a,
        commit_b)


def write_repair_instance(
        potential_diff: BuildRepairInstanceOutput,
        repair_file_directory: Path,
        repair_instance_db: RepairInstanceDB):
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
            potential_diff,
            repair_file_directory,
            repair_instance_db)
        atomic_write(file_path, potential_diff)
    elif isinstance(potential_diff, Except):
        ...
    else:
        raise TypeError(
            f"Type {type(potential_diff)} is not recognized and can't be "
            "written.")


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
        repair_save_directory: Path,
        cache_format_extension: str = "yml",
        prepare_pairs: PreparePairsFunctionSignature = prepare_state_pairs,
        miner: MiningFunctionSignature = default_miner,
        serial: bool = False,
        max_workers: Optional[int] = None,
        chunk_size: int = 1):
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
    prepare_pairs : PreparePairsFunctionSignature, optional
        Function to prepare pairs of cache item labels to be used for
        repair instance mining
    miner : MiningFunctionSignature, optional
        Worker function to mine repair instances given a pair of cache
        objects
    serial : bool, optional
        Flag to control parallel execution, by default False. If True,
        use serial execution. If False, use parallel execution.
    max_workers : int or None, optional
        Maximum number of parallel workers to allow, by default None,
        which sets the value to min(32, number of cpus + 4)
    chunk_size : int, optional
        Size of job chunk sent to each worker, by default 1
    """
    with CoqProjectBuildCacheServer() as cache_server:
        db_file = repair_save_directory / "repair_records.sqlite3"
        with RepairInstanceDB(db_file) as db_instance:
            cache_args = (cache_server, cache_root, cache_format_extension)
            cache_item_pairs = prepare_pairs(*cache_args)
            jobs = [
                (cache_args,
                 repair_save_directory,
                 db_instance,
                 miner,
                 a,
                 b) for a,
                b in cache_item_pairs
            ]
            if serial:
                for job in jobs:
                    result = build_repair_instance_star(job)
                    if isinstance(result, Except):
                        print(result.trace)
                        raise result.exception
            else:
                kwargs = {}
                if max_workers is not None:
                    kwargs["max_workers"] = max_workers
                kwargs["chunksize"] = chunk_size
                process_map(
                    build_repair_instance_star,
                    jobs,
                    desc="Repair Mining",
                    **kwargs)
