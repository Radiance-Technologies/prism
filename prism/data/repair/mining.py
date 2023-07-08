"""
Mine repair instances by looping over existing project build cache.
"""
import enum
import logging
import os
import queue
import select
import shutil
import sqlite3
import typing
from dataclasses import asdict, dataclass
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

import pandas as pd
from tqdm import tqdm
from traceback_with_variables import format_exc

from prism.data.cache.server import CacheObjectStatus, CoqProjectBuildCache
from prism.data.cache.types.project import ProjectCommitData
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
from prism.util.io import Fmt, atomic_write
from prism.util.manager import ManagedServer
from prism.util.path import append_suffix, with_suffixes
from prism.util.radpytools.path import PathLike

BuildRepairInstanceOutput = Optional[Union[ProjectCommitDataRepairInstance,
                                           Except[None]]]
"""
Type hint for the output of build_repair_instance_star.
"""
RepairMiner = Callable[[ProjectCommitDataErrorInstance,
                        ProjectCommitData],
                       ProjectCommitDataRepairInstance]
"""
Signature of the function used to create repair instances.
"""
ProjectCommitHashMap = Optional[Dict[str, Optional[List[str]]]]
PreparePairsReturn = List[Tuple[CacheObjectStatus, CacheObjectStatus]]
PreparePairsFunction = Callable[
    [Path,
     str,
     MetadataStorage,
     ProjectCommitHashMap],
    PreparePairsReturn]
"""
Signature of the function used to prepare cache item label pairs for
repair instance mining.
"""
CacheLabel = Dict[str, str]
"""
Dictionary labeling a cache object (project name, commit sha,
Coq version).
"""
AugmentedErrorInstance = Tuple[ProjectCommitDataErrorInstance,
                               ProjectCommitData,
                               ChangeSelection]
"""
A tuple containing an error instance, with the repaired state used to
produce it, and the corresponding change selection.
"""
AugmentedChangeSelectionList = Tuple[ProjectCommitData,
                                     ProjectCommitData,
                                     ProjectCommitDataDiff,
                                     List[ChangeSelection]]
"""
A tuple containing a list of changesets along with the states and diff
to which each changeset corresponds.
"""


@dataclass(frozen=True)
class ChangeSetMiningJob:
    """
    Job for mining changesets for later creation of error instances.
    """

    label_a: CacheObjectStatus
    """
    The label corresponding to the initial state.
    """
    label_b: CacheObjectStatus
    """
    The label corresponding to the repaired state.
    """
    cache_root: Path
    """
    Path to the root of the cache to load items from
    """
    cache_fmt_extension: str
    """
    Extension to expect for the individual cache files
    """
    changeset_miner: ChangeSetMiner
    """
    The callable used to mine ChangeSelection objects
    """
    repair_mining_logger: 'RepairMiningLogger'
    """
    The object used to log error messages and other debug messages
    encountered during mining.
    """
    fast: bool
    """
    Whether to perform fast mining or not, i.e., whether to discard
    unnecessary extracted data and yield only Git-based instances.
    """


@dataclass(frozen=True)
class ErrorInstanceJob:
    """
    Job for creating error instances.
    """

    initial_state: ProjectCommitData
    """
    A state of the project.
    """
    repaired_state: ProjectCommitData
    """
    A state based on the `initial_state` that contains at least one
    change to a command.
    """
    diff: ProjectCommitDataDiff
    """
    A precomputed diff between `initial_state` and `final_state`.
    """
    change_selection: ChangeSelection
    """
    The change selection that gives rise to this error instance and
    repaired state
    """
    repair_mining_logger: 'RepairMiningLogger'
    """
    The object used to log error messages and other debug messages
    encountered during mining.
    """


@dataclass(frozen=True)
class RepairInstanceJob:
    """
    Job for creating repair instances.
    """

    error_instance: ProjectCommitDataErrorInstance
    """
    A preconstructed example of an error.
    """
    repaired_state: ProjectCommitData
    """
    A state based on that of `error_instance` that is presumed to be
    repaired.
    """
    change_selection: ChangeSelection
    """
    The change selection that gives rise to this error instance and
    repaired state
    """
    repair_instance_db_directory: Path
    """
    Path to directory that contains the database for recording new
    repair instances saved to disk
    """
    miner: RepairMiner
    """
    Function used to mine repair instances
    """
    repair_mining_logger: 'RepairMiningLogger'
    """
    Object used to log errors and other debug messages during repair
    instance building
    """


class StopWorkSentinel:
    """
    Place on job queue to allow worker function to exit.
    """

    pass


class JobStatus(enum.Enum):
    """
    An enum to communicate status of a parallel job.
    """

    QUEUED = enum.auto()
    """
    Symbolizes the start of a job.
    """
    PROGRESSED = enum.auto()
    """
    Symbolizes the completion of a jobs' subtask.
    """
    COMPLETED = enum.auto()
    """
    Symbolizes the conclusion of a job (technically, the dequeuing of
    each of its subtasks).
    """


class JobType(enum.Enum):
    """
    The type of a parallel job.
    """

    ERROR_INSTANCE = enum.auto()
    """
    Error instance creation.
    """
    REPAIR_INSTANCE = enum.auto()
    """
    Repair instance creation.
    """


@dataclass(frozen=True)
class JobID:
    """
    Identifies a job.
    """

    label_a: CacheObjectStatus
    label_b: CacheObjectStatus
    job_type: JobType

    def __str__(self) -> str:  # noqa: D105
        job_type = "errors" if self.job_type == JobType.ERROR_INSTANCE else "repairs"
        return (
            f"Mining {job_type}: {self.label_a.project}"
            f"@{self.label_a.commit_hash[:8]}({self.label_a.coq_version})"
            f"..{self.label_b.commit_hash[:8]}({self.label_b.coq_version})")


@dataclass(frozen=True)
class JobStatusMessage:
    """
    Place in worker-parent queue to communicate job completions.
    """

    job_id: JobID
    job_size: int
    status: JobStatus

    @classmethod
    def from_job(
            cls,
            job: Union[ErrorInstanceJob,
                       RepairInstanceJob],
            size: int,
            status: JobStatus) -> 'JobStatusMessage':
        """
        Create a message for a given job.
        """
        if isinstance(job, ErrorInstanceJob):
            job_id = JobID(
                CacheObjectStatus.from_metadata(
                    job.initial_state.project_metadata),
                CacheObjectStatus.from_metadata(
                    job.repaired_state.project_metadata),
                JobType.ERROR_INSTANCE)
        else:
            job_id = JobID(
                CacheObjectStatus.from_metadata(
                    job.error_instance.project_metadata),
                CacheObjectStatus.from_metadata(
                    job.repaired_state.project_metadata),
                JobType.REPAIR_INSTANCE)
        return JobStatusMessage(job_id, size, status)


class LoopControl(enum.Enum):
    """
    Control-flow enums for managing the main mining loop.
    """

    PASS = enum.auto()
    """
    Continue with the current iteration.
    """
    CONTINUE = enum.auto()
    """
    Continue to the next iteration without completing the current one.
    """
    BREAK = enum.auto()
    """
    Break out of the loop.
    """


class CommitPairDBRecord(NamedTuple):
    """
    A unique ID for a pair of commits in the repair instance database.
    """

    project_name: str
    """
    The name of the project to which the repair instance belongs.
    """
    initial_commit_sha: str
    """
    The initial commit from which the repair instance was mined.
    """
    repaired_commit_sha: str
    """
    The final commit from which the repair instance was mined.
    """
    initial_coq_version: str
    """
    The Coq version for which data for the initial commit was extracted.
    """
    repaired_coq_version: str
    """
    The Coq version for which data for the final commit was extracted.
    """

    def asdict(self) -> Dict[str, str]:
        """
        Get the record sans `id`.
        """
        return self._asdict()

    @classmethod
    def from_metadata(
            cls,
            initial_metadata: ProjectMetadata,
            repaired_metadata: ProjectMetadata) -> 'CommitPairDBRecord':
        """
        Create a commit pair record from a pair of commits' metadata.

        Raises
        ------
        ValueError
            If the given metadata come from different projects.
        TypeError
            If any of the commit SHAs for Coq versions in the given
            metadata are `None``.
        """
        if initial_metadata.project_name != repaired_metadata.project_name:
            raise ValueError(
                "Cannot create commit pair from different projects "
                f"{initial_metadata.project_name} and {repaired_metadata.project_name}"
            )
        if initial_metadata.commit_sha is None:
            raise TypeError("Initial commit SHA must not be None")
        if repaired_metadata.commit_sha is None:
            raise TypeError("Repaired commit SHA must not be None")
        if initial_metadata.coq_version is None:
            raise TypeError("Initial commit SHA must not be None")
        if repaired_metadata.coq_version is None:
            raise TypeError("Repaired commit SHA must not be None")
        return cls(
            initial_metadata.project_name,
            initial_metadata.commit_sha,
            repaired_metadata.commit_sha,
            initial_metadata.coq_version,
            repaired_metadata.coq_version)

    @classmethod
    def from_repair_instance_record(
            cls,
            record: 'RepairInstanceDBRecord') -> 'CommitPairDBRecord':
        """
        Create a commit pair record from a repair instance record.
        """
        return cls(*record[: 5])


class RepairInstanceDBRecord(NamedTuple):
    """
    A row in a repair instance database.
    """

    project_name: str
    """
    The name of the project to which the repair instance belongs.
    """
    initial_commit_sha: str
    """
    The initial commit from which the repair instance was mined.
    """
    repaired_commit_sha: str
    """
    The final commit from which the repair instance was mined.
    """
    initial_coq_version: str
    """
    The Coq version for which data for the initial commit was extracted.
    """
    repaired_coq_version: str
    """
    The Coq version for which data for the final commit was extracted.
    """
    added_commands: str
    """
    A serialized list of command IDs added between the commits.
    """
    affected_commands: str
    """
    A serialized list of command IDs affected between the commits.

    A command was affected if its extracted data other than its text was
    changed.
    """
    changed_commands: str
    """
    A serialized list of command IDs whose text changed between commits.
    """
    dropped_commands: str
    """
    A serialized list of command IDs that were dropped between commits.
    """
    id: Optional[int] = None
    """
    A surrogate primary key.
    """
    file_name: Optional[str] = None
    """
    The path to the repair instance corresponding to this record.

    The path is relative to the root directory of the repair instance
    database.
    """

    def __eq__(self, other: object) -> bool:
        """
        Test equality of two records according to natural primary keys.
        """
        if not isinstance(other, RepairInstanceDBRecord):
            return NotImplemented
        return typing.cast(tuple, self[:-2]) == other[:-2]

    @property
    def commit_pair(self) -> CommitPairDBRecord:
        """
        The pair of commits from which this instance was mined.
        """
        return CommitPairDBRecord.from_repair_instance_record(self)

    def asdict(self) -> Dict[str, str]:
        """
        Get the record sans `id`.
        """
        return self._asdict()

    @classmethod
    def from_row(
        cls,
        row: Tuple[int,
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
    ) -> 'RepairInstanceDBRecord':
        """
        Create a record from a raw database row.
        """
        return cls(
            id=row[0],
            project_name=row[1],
            initial_commit_sha=row[2],
            repaired_commit_sha=row[3],
            initial_coq_version=row[4],
            repaired_coq_version=row[5],
            added_commands=row[6],
            affected_commands=row[7],
            changed_commands=row[8],
            dropped_commands=row[9],
            file_name=row[10])


class RepairInstanceDB:
    """
    Database for storing information about saved repair instances.

    This is a single-table database. Each row in the table maps a set of
    identifying details of a repair instance to the filename that stores
    the serialized, saved repair instance.
    """

    # TODO: Normalize database using CommitPairDBRecord and
    # object-relational DB (sqlalchemy)

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
    _sql_create_natural_primary_key = """
        CREATE UNIQUE INDEX natural_primary_key
        ON records(
            project_name,
            initial_commit_sha,
            repaired_commit_sha,
            initial_coq_version,
            repaired_coq_version,
            added_commands,
            affected_commands,
            changed_commands,
            dropped_commands
        );
        """
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
    _sql_get_all_records = """
        SELECT *
        FROM records
        ORDER BY id;
        """
    _fmt: Fmt = Fmt.json

    def __init__(self, db_directory: PathLike):
        self.db_directory = Path(db_directory)
        """
        The directory containing the database.
        """
        self.db_directory.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_location))
        self.cursor = self.connection.cursor()
        self.create_table()

    def __contains__(self, record: object) -> bool:
        """
        Return whether the database contains the given object.

        Raises
        ------
        TypeError
            If `record` is not a `CommitPairDBRecord` or
            `RepairInstanceDBRecord`.
        """
        if not isinstance(record, (CommitPairDBRecord, RepairInstanceDBRecord)):
            raise TypeError(f"Unsupported record type: {type(record)}")
        elif isinstance(record, RepairInstanceDBRecord):
            return self.get(record).id is not None
        else:
            return len(self.get_repairs(record)) > 0

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

    @property
    def db_location(self) -> Path:
        """
        Get the path to the SQLite3 database file.
        """
        return self.db_directory / ".sqlite3"

    def create_table(self):
        """
        Create the one table this database requires.
        """
        self.cursor.execute(self._sql_create_records_table)
        self.cursor.execute(self._sql_create_natural_primary_key)
        self.connection.commit()

    def get(self, record: RepairInstanceDBRecord) -> RepairInstanceDBRecord:
        """
        Get a complete record from the database.

        If the record is not contained in the database, then its ID and
        filename will each be None.
        """
        record_dict = record.asdict()
        record_dict.pop("id")
        record_dict.pop("file_name")
        self.cursor.execute(self._sql_get_record, record_dict)
        rows = self.cursor.fetchall()
        if not rows:
            return RepairInstanceDBRecord(*record[:-2])
        assert len(rows) == 1, \
            "There are duplicate rows in the records table."
        return RepairInstanceDBRecord.from_row(rows[0])

    def get_repairs(self,
                    record: CommitPairDBRecord) -> Set[RepairInstanceDBRecord]:
        """
        Get all repair instances associated with a commit pair.
        """
        self.cursor.execute(
            self._sql_get_records_for_commit_pair,
            record.asdict())
        rows = self.cursor.fetchall()
        records = {RepairInstanceDBRecord.from_row(row) for row in rows}
        return records

    def insert(self, record: RepairInstanceDBRecord) -> int:
        """
        Insert a new record into the database.

        Raises
        ------
        sqlite3.IntegrityError
            If this record already exists in the database.
        """
        record_dict = record.asdict()
        record_dict.pop("id")
        self.cursor.execute(self._sql_insert_record, record_dict)
        self.connection.commit()
        inserted_row = self.get(record)
        assert inserted_row.id is not None, \
            "No id was returned after the last record insertion."
        return inserted_row.id

    def insert_record_get_path(
            self,
            record: Union[CommitPairDBRecord,
                          RepairInstanceDBRecord],
            change_selection: Optional[ChangeSelection] = None) -> Path:
        """
        Insert a repair instance record into the database.

        Parameters
        ----------
        record : CommitPairDBRecord | RepairInstanceDBRecord
            A commit pair used for mining repairs or a mined repair
            record itself.
        change_selection : Optional[ChangeSelection], optional
            The selected changes that further identify the record,
            by default None.

        Returns
        -------
        Path
            The reserved absolute path to the new repair instance file.
        ValueError
            If `change_selection` is None and `record` is an instance of
            `CommitPairDBRecord` or if `change_selection` is not None
            and `record` is an instance of `RepairInstanceDBRecord`.
        """
        # Summary:
        # * Insert a record with a place-holder file name.
        # * Immediately fetch the new row back with its auto-incremented
        #   row id.
        # * Fetch all rows matching the project name and commit pair and
        #   Coq version pair.
        # * Get the row indices from each returned row, sort them, and
        #   get the index of the just-inserted row in that list.
        # * Use this index to name the file, along with the project
        #   name, commit sha pair, and Coq version pair
        # * Update the row with the newly-computed file name.
        # * Return the new file name.
        if isinstance(record, CommitPairDBRecord):
            if change_selection is None:
                raise ValueError(
                    "A change selection must be specified for the commit pair"
                    f" {record}")
            commit_pair = record
            record = RepairInstanceDBRecord(
                *commit_pair,
                file_name="record-n",
                **change_selection.as_joined_dict())  # type: ignore
        else:
            commit_pair = record.commit_pair
            if change_selection is not None:
                raise ValueError(
                    "An additional change selection must not be specified for the"
                    f" record from commit pair {record.commit_pair}")
        recent_id = self.insert(record)
        associated_repairs = self.get_repairs(commit_pair)
        change_index = len(associated_repairs) - 1
        new_file_name = self.get_file_name(commit_pair, change_index)
        self.cursor.execute(
            self._sql_update_file_name,
            {
                'file_name': str(new_file_name),
                'row_id': recent_id
            })
        self.connection.commit()
        return self.db_directory / new_file_name

    def get_record(
            self,
            commit_pair: CommitPairDBRecord,
            change_selection: ChangeSelection
    ) -> Optional[RepairInstanceDBRecord]:
        """
        Get a record from the records table if it exists.

        Parameters
        ----------
        commit_pair : CommitPairDBRecord
            A commit pair used for mining repairs.
        change_selection : ChangeSelection
            The selected changes that further identify the record

        Returns
        -------
        Optional[RepairInstanceDBRecord]
            The record as a dictionary, or None if no record was found

        Raises
        ------
        RuntimeError
            If multiple records are found for the query. This shouldn't
            be able to happen, and if it does, it indicates a bug.
        """
        record_to_get = RepairInstanceDBRecord(
            *commit_pair,
            file_name="record-n",
            **change_selection.as_joined_dict())  # type: ignore
        return self.get(record_to_get)

    def get_record_from_file_name(self,
                                  file_name: str
                                  ) -> Optional[RepairInstanceDBRecord]:
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
        rows = self.cursor.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise RuntimeError(
                f"There is more than 1 row for file {file_name}.")
        return RepairInstanceDBRecord.from_row(rows[0])

    def get_records_iter(self) -> Iterator[RepairInstanceDBRecord]:
        """
        Get an iterator over the database's records.

        The records will be ordered by the numeric surrogate primary key
        that identifies each record (i.e., the records will be ordered
        by the order in which they were originally inserted).
        """
        self.cursor.execute(self._sql_get_all_records)
        records = self.cursor.fetchall()
        yield from (RepairInstanceDBRecord.from_row(row) for row in records)

    def merge(self,
              other: 'RepairInstanceDB',
              copy: bool = True) -> List[Tuple[Path,
                                               Path]]:
        """
        Add all non-duplicate records in another database to this one.

        Repair instance files will also be copied to their appropriate
        location in this database.

        Parameters
        ----------
        other : RepairInstanceDB
            Another repair instance database.
        copy : bool, optional
            If True, then go ahead and copy repair instance files from
            the `other` database to this one.

        Returns
        -------
        List[Tuple[Path, Path]]
            A list of pairs of paths mapping repair instance files
            indexed by `other` to their new locations indexed in `self`
            after the merge.

        Raises
        ------
        FileNotFoundError
            If `copy` is True but one of the repair instance files could
            not be found.
        """
        path_map: List[Tuple[Path, Path]] = []
        for record in other.get_records_iter():
            if record not in self:
                try:
                    new_path = self.insert_record_get_path(record)
                except sqlite3.IntegrityError:
                    # the record already exists in the database
                    pass
                else:
                    assert record.file_name is not None, \
                        "The old file path must be defined"
                    old_path = other.db_directory / record.file_name
                    if copy:
                        shutil.copy2(old_path, new_path)
                    path_map.append((old_path, new_path))
        return path_map

    @classmethod
    def get_file_name(
            cls,
            commit_pair: CommitPairDBRecord,
            change_index: int) -> Path:
        """
        Get the canonical filename for the identified repair example.

        Parameters
        ----------
        commit_pair : CommitPairDBRecord
            A commit pair used for mining repairs.
        change_index : int
            The index of a change between the indicated pair of commits.
            By definition, this index gives the order by which repairs
            were mined from the commit pair.

        Returns
        -------
        Path
            The path to the file containing the requested change
            relative to the root of the repair instance database.
        """
        filename: PathLike = "-".join(
            [
                "repair",
                commit_pair.project_name,
                commit_pair.initial_commit_sha,
                commit_pair.repaired_commit_sha,
                CoqProjectBuildCache.format_coq_version(
                    commit_pair.initial_coq_version),
                CoqProjectBuildCache.format_coq_version(
                    commit_pair.repaired_coq_version),
                str(change_index)
            ])
        filename = append_suffix(filename, f".{cls._fmt.exts[0]}")
        filename = commit_pair.project_name / filename
        return filename

    @classmethod
    def get_compressed_file_name(cls, file_name: PathLike) -> Path:
        """
        Get the path to the diff-compressed version of a repair example.

        Parameters
        ----------
        file_name : PathLike
            The canonical path to the full repair example containing a
            serialized `ProjectCommitDataRepairInstance`.

        Returns
        -------
        Path
            The path to the file that should contain the corresponding
            `GitRepairInstance`.
        """
        file_name = Path(file_name)
        return with_suffixes(file_name, [".git", file_name.suffix])

    @classmethod
    def union(
            cls,
            db_directory: PathLike,
            *databases: 'RepairInstanceDB') -> 'RepairInstanceDB':
        """
        Merge multiple repair instance databases in a new database.

        Parameters
        ----------
        db_directory : PathLike
            The root directory of the merged database.
        databases : tuple of RepairInstanceDB
            An iterable collection of one or more repair instance
            databases.

        Returns
        -------
        RepairInstanceDB
            The union of each of the given databases rooted at the given
            directory.
        """
        result = RepairInstanceDB(db_directory)
        for database in databases:
            result.merge(database)
        return result


class RepairMiningLogger:
    """
    Logger for writing logs during repair mining process.
    """

    def __init__(self, repair_instance_db_directory: PathLike, level: int):
        self.logger = logging.getLogger(__name__)
        # Get rid of the stdout handler
        for handler in self.logger.handlers:
            self.logger.removeHandler(handler)
        self.logger.setLevel(level)
        self.handler = logging.FileHandler(
            str(Path(repair_instance_db_directory) / "repair_mining_log.txt"))
        self.handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.handler.setLevel(level)
        self.logger.addHandler(self.handler)

    def write_exception_log(self, exception: Except[None]):
        """
        Write a log entry for the given exception.

        logging.Logger objects are not multi-processing-safe, so this
        method is synchronized to prevent simultaneous write attempts.

        Parameters
        ----------
        exception : Except[None]
            Exception to write a log entry for
        """
        self.logger.exception(exception.exception)
        self.logger.error(f"Traceback: {exception.trace}")

    def write_debug_log(self, message: str):
        """
        Write a debug message.

        Parameters
        ----------
        message : str
            Message to write as a debug message to the logger.
        """
        self.logger.debug(message)


class RepairMiningLoggerServer(ManagedServer[RepairMiningLogger]):
    """
    A BaseManager-derived server for managing repair mining logs.
    """

    pass


def build_repair_instance(
        error_instance: ProjectCommitDataErrorInstance,
        repaired_state: ProjectCommitData,
        change_selection: ChangeSelection,
        repair_instance_db_directory: Path,
        miner: RepairMiner,
        repair_mining_logger: RepairMiningLogger) -> BuildRepairInstanceOutput:
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
    repair_instance_db_directory : Path
        Path to database for recording new repair instances saved to
        disk
    miner : RepairMiner
        Function used to mine repair instances
    repair_mining_logger : RepairMiningLogger
        Object used to log errors and other debug messages during repair
        instance building

    Returns
    -------
    BuildRepairInstanceOutput
        If repair mining was successful, return the output
        If repair mining raise an error, return an Except[None]
        If there was no error but no repair instance was produced,
        return None
    """
    result = None
    try:
        with RepairInstanceDB(repair_instance_db_directory) as db_instance:
            initial_metadata = error_instance.project_metadata
            repaired_metadata = repaired_state.project_metadata
            commit_pair = CommitPairDBRecord.from_metadata(
                initial_metadata,
                repaired_metadata)
            if db_instance.get_record(commit_pair, change_selection) is None:
                result = miner(error_instance, repaired_state)
            else:
                result = None
    except Exception as e:
        result = Except(None, e, format_exc(e))
        repair_mining_logger.write_exception_log(result)
    finally:
        if result is not None:
            write_repair_instance(
                result,
                change_selection,
                repair_instance_db_directory,
                repair_mining_logger,
                repaired_state.project_metadata)
    return result


def build_repair_instance_star(
        args: RepairInstanceJob) -> BuildRepairInstanceOutput:
    """
    Split arguments and call build_repair_instance.

    Parameters
    ----------
    args : RepairInstanceJob
        Bundled arguments for build_repair_instance

    Returns
    -------
    BuildRepairInstanceOutput
        If repair mining was successful, return the output
        If repair mining raise an error, return an Except[None]
        If there was no error but no repair instance was produced,
        return None
    """
    return build_repair_instance(
        args.error_instance,
        args.repaired_state,
        args.change_selection,
        args.repair_instance_db_directory,
        args.miner,
        args.repair_mining_logger)


def build_error_instance(
    initial_state: ProjectCommitData,
    repaired_state: ProjectCommitData,
    diff: ProjectCommitDataDiff,
    changeset: ChangeSelection,
    repair_mining_logger: RepairMiningLogger
) -> Union[AugmentedErrorInstance,
           Except[None]]:
    """
    Construct an error instance from a pair of cache items.

    Parameters
    ----------
    initial_state : ProjectCommitData
        An initial state that may or may not contain an error.
    repaired_state : ProjectCommitData
        A state based on `initial_state`.
    diff : ProjectCommitDataDiff
        A precomputed diff between `initial_state` and `repaired_state`.
    changeset : ChangeSelection
        A selection of changes from `diff`.
    repair_mining_logger : RepairMiningLogger
        Object used to log errors and other debug messages during repair
        instance building

    Returns
    -------
    AugmentedErrorInstance | Except[None]
        An augmented error instance if successful or Excep[None] if an
        error was encountered.
    """
    try:
        error_instance = ProjectCommitDataErrorInstance.make_error_instance(
            initial_state,
            repaired_state,
            diff,
            changeset,
            ProjectCommitDataErrorInstance.default_get_error_tags)
    except Exception as e:
        result = Except(None, e, format_exc(e))
        repair_mining_logger.write_exception_log(result)
    else:
        result = (error_instance, repaired_state, changeset)
    return result


def build_error_instance_star(
        args: ErrorInstanceJob) -> Union[AugmentedErrorInstance,
                                         Except[None]]:
    """
    Split arguments and call build_repair_instance.

    Parameters
    ----------
    args : RepairInstanceJob
        Bundled arguments for build_repair_instance

    Returns
    -------
    BuildRepairInstanceOutput
        If repair mining was successful, return the output
        If repair mining raise an error, return an Except[None]
        If there was no error but no repair instance was produced,
        return None
    """
    return build_error_instance(
        args.initial_state,
        args.repaired_state,
        args.diff,
        args.change_selection,
        args.repair_mining_logger)


def mine_changesets_from_label_pair(
        label_a: CacheObjectStatus,
        label_b: CacheObjectStatus,
        cache_root: Path,
        cache_fmt_extension: str,
        changeset_miner: ChangeSetMiner,
        repair_mining_logger: RepairMiningLogger,
        fast: bool) -> Union[AugmentedChangeSelectionList,
                             Except[None]]:
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
    cache_root : Path
        Path to the root of the cache to load items from
    cache_fmt_extension : str
        Extension to expect for the individual cache files
    changeset_miner : ChangeSetMiner
        The callable used to mine ChangeSelection objects
    repair_mining_logger : RepairMiningLogger
        The object used to log error messages and other debug messages
        encountered during mining.
    fast : bool
        If True, then accelerate mining by discarding extracted fields
        that are not required for alignment and identification of
        repairs, yielding only Git-based repair instances.
        Otherwise, keep all data and yield commit-data-based repair
        instances as well.

    Returns
    -------
    Union[AugmentedChangeSelectionList, Except[None]]
        An augmented list of selected changesets if successful or an
        Except[None] object if there's an error.
    """
    try:
        cache = CoqProjectBuildCache(cache_root, cache_fmt_extension)
        initial_state = cache.get(
            label_a.project,
            label_a.commit_hash,
            label_a.coq_version)
        repair_mining_logger.write_debug_log(
            "build_error_instances_from_label_pair: Finished loading cache for"
            f" label a: {label_a}.")
        repaired_state = cache.get(
            label_b.project,
            label_b.commit_hash,
            label_b.coq_version)
        repair_mining_logger.write_debug_log(
            "build_error_instances_from_label_pair: Finished loading cache for"
            f" label b: {label_b}.")
        if fast:
            # discard ASTs, goals, hypotheses, feedback, and identifiers
            # XXX: Could this be made temporary and restored at the end?
            for _, command in initial_state.commands:
                command.discard_data()
            for _, command in repaired_state.commands:
                command.discard_data()
        commit_diff = typing.cast(
            ProjectCommitDataDiff,
            ProjectCommitDataDiff.from_commit_data(
                initial_state,
                repaired_state,
                default_align))
        result = (
            initial_state,
            repaired_state,
            commit_diff,
            list(changeset_miner(initial_state,
                                 commit_diff)))
    except Exception as e:
        result = Except(None, e, format_exc(e))
        repair_mining_logger.write_exception_log(result)
    return result


def mine_changesets_from_label_pair_star(
    args: ChangeSetMiningJob) -> Union[AugmentedChangeSelectionList,
                                       Except[None]]:
    """
    Split arguments and call build_error_instances_from_label_pair.

    Parameters
    ----------
    args : ErrorInstanceJob
        Bundled arguments for build_error_instances_from_label_pair.

    Returns
    -------
    Union[List[AugmentedErrorInstance], Except[None]]
        A list of augmented error instances if successful or an
        Except[None] object if there's an error.
    """
    return mine_changesets_from_label_pair(
        args.label_a,
        args.label_b,
        args.cache_root,
        args.cache_fmt_extension,
        args.changeset_miner,
        args.repair_mining_logger,
        args.fast)


def write_repair_instance(
        potential_diff: BuildRepairInstanceOutput,
        change_selection: ChangeSelection,
        repair_instance_db_directory: Path,
        repair_mining_logger: RepairMiningLogger,
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
    repair_instance_db_directory : Path
        Path to database for recording new repair instances saved to
        disk
    repair_mining_logger : RepairMiningLogger
        Object used to log errors and other debug messages
    repaired_state_metadata : ProjectMetadata
        Metadata for the repaired state, used to determine the
        information to record for this instance.

    Raises
    ------
    TypeError
        If potential_diff is neither of ProjectCommitDataRepairInstance
        nor of Except[None].
    """
    if isinstance(potential_diff, ProjectCommitDataRepairInstance):
        with RepairInstanceDB(
                repair_instance_db_directory) as repair_instance_db:
            initial_metadata = \
                potential_diff.error.initial_state.project_state.project_metadata
            assert initial_metadata.commit_sha is not None
            assert initial_metadata.coq_version is not None
            assert repaired_state_metadata.commit_sha is not None
            assert repaired_state_metadata.coq_version is not None

            file_path = repair_instance_db.insert_record_get_path(
                CommitPairDBRecord.from_metadata(
                    initial_metadata,
                    repaired_state_metadata),
                change_selection)
            atomic_write(
                file_path,
                potential_diff,
                use_gzip_compression_for_serializable=True)
            compressed_file_path = repair_instance_db.get_compressed_file_name(
                file_path)
            atomic_write(
                compressed_file_path,
                potential_diff.compress(),
                use_gzip_compression_for_serializable=False)
    elif isinstance(potential_diff, Except):
        repair_mining_logger.write_exception_log(potential_diff)
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
    commit_tuples = []
    for ch in commit_hashes:
        try:
            commit_tuples.append((repo.commit(ch).authored_datetime, ch))
        except ValueError:
            # Skip if commit can't be checked out
            continue
    dated_commit_hashes = sorted(commit_tuples)
    return [
        (dch1[1],
         dch2[1]) for dch1,
        dch2 in zip(dated_commit_hashes,
                    dated_commit_hashes[1 :])
    ]


def build_error_instance_creation_inputs(
        changeset_mining_results: Union[AugmentedChangeSelectionList,
                                        Except[None]],
        repair_mining_logger: RepairMiningLogger) -> List[ErrorInstanceJob]:
    """
    Build a repair instance job from error instance results.

    Parameters
    ----------
    changest_mining_results : Union[AugmentedChangeSelectionList,
                                   Except[None]]
        The output of the changeset miner.
    repair_mining_logger : RepairMiningLogger
        The object used to log errors and debug messages during repair
        mining

    Returns
    -------
    List[ErrorInstanceJob]
        A list of prepared error instance creation jobs for dispatch to
        worker functions
    """
    error_instance_jobs: List[ErrorInstanceJob] = []
    if isinstance(changeset_mining_results, Except):
        return []
    initial_state, repaired_state, diff, change_selections = changeset_mining_results
    for change_selection in change_selections:
        error_instance_job = ErrorInstanceJob(
            initial_state,
            repaired_state,
            diff,
            change_selection,
            repair_mining_logger)
        error_instance_jobs.append(error_instance_job)
    return error_instance_jobs


def build_repair_instance_mining_inputs(
        error_instance_results: Union[AugmentedErrorInstance,
                                      List[AugmentedErrorInstance],
                                      Except[None]],
        repair_instance_db_directory: Path,
        repair_miner: RepairMiner,
        repair_mining_logger: RepairMiningLogger) -> List[RepairInstanceJob]:
    r"""
    Build a repair instance job from error instance results.

    Parameters
    ----------
    error_instance_results : Union[AugmentedErrorInstance, \
                                   List[AugmentedErrorInstance], \
                                   Except[None]]
        The output of the error instance builder
    repair_instance_db_file : Path
        The path to the repair instance record database
    repair_miner : RepairMiner
        The function used to mine repairs
    repair_mining_logger : RepairMiningLogger
        The object used to log errors and debug messages during repair
        mining

    Returns
    -------
    List[RepairInstanceJob]
        A list of prepared repair instance mining jobs for dispatch to
        worker functions
    """
    repair_instance_jobs: List[RepairInstanceJob] = []
    if isinstance(error_instance_results, Except):
        return []
    elif not isinstance(error_instance_results, list):
        error_instance_results = [error_instance_results]
    for error_instance_result in error_instance_results:
        if isinstance(error_instance_result, Except):
            continue
        error_instance, repaired_state, change_selection = error_instance_result
        repair_instance_job = RepairInstanceJob(
            error_instance,
            repaired_state,
            change_selection,
            repair_instance_db_directory,
            repair_miner,
            repair_mining_logger)
        repair_instance_jobs.append(repair_instance_job)
    return repair_instance_jobs


def _mine_repairs(
        repair_instance_job_queue: queue.Queue[RepairInstanceJob],
        worker_to_parent_queue: queue.Queue[Union[Except,
                                                  JobStatusMessage]],
        skip_errors: bool) -> LoopControl:
    """
    Mine repairs from mined errors.
    """
    try:
        repair_job = repair_instance_job_queue.get_nowait()
    except Empty:
        return LoopControl.PASS
    else:
        if isinstance(repair_job, RepairInstanceJob):
            result = build_repair_instance_star(repair_job)
            if not skip_errors and isinstance(result, Except):
                worker_to_parent_queue.put(result)
                return LoopControl.BREAK
            worker_to_parent_queue.put(
                JobStatusMessage.from_job(repair_job,
                                          1,
                                          JobStatus.PROGRESSED))
        else:
            raise RuntimeError(
                f"Unexpected type {type(repair_job)} for repair_job.")
        # Don't automatically go to building error instances. Focus
        # on clearing the repair instance queue out.
        return LoopControl.CONTINUE


def _mine_errors(
        error_instance_job_queue: queue.Queue[Union[ErrorInstanceJob,
                                                    JobStatusMessage]],
        repair_instance_job_queue: queue.Queue[RepairInstanceJob],
        worker_to_parent_queue: queue.Queue[Union[Except,
                                                  JobStatusMessage]],
        repair_instance_db_directory: Path,
        repair_miner: RepairMiner,
        skip_errors: bool) -> LoopControl:
    """
    Mine errors from mined changesets.
    """
    try:
        error_instance_job = error_instance_job_queue.get_nowait()
    except Empty:
        return LoopControl.PASS
    else:
        if isinstance(error_instance_job, ErrorInstanceJob):
            result = build_error_instance_star(error_instance_job)
            if not skip_errors and isinstance(result, Except):
                worker_to_parent_queue.put(result)
                return LoopControl.PASS
            # If skip_errors is true and result is an Except, the
            # following will immediately return an empty list.
            repair_instance_jobs = build_repair_instance_mining_inputs(
                result,
                repair_instance_db_directory,
                repair_miner,
                error_instance_job.repair_mining_logger)
            for repair_instance_job in repair_instance_jobs:
                repair_instance_job_queue.put(repair_instance_job)
            worker_to_parent_queue.put(
                JobStatusMessage.from_job(
                    error_instance_job,
                    1,
                    JobStatus.PROGRESSED))
        elif isinstance(error_instance_job, JobStatusMessage):
            worker_to_parent_queue.put(error_instance_job)
        else:
            raise RuntimeError(
                f"Unexpected type {type(error_instance_job)} "
                "for error_instance_job.")
        # Don't automatically go to mining changesets. Focus
        # on clearing the error instance queue out.
        return LoopControl.CONTINUE


def _mine_changesets(
        changeset_mining_job_queue: queue.Queue[ChangeSetMiningJob],
        error_instance_job_queue: queue.Queue[Union[ErrorInstanceJob,
                                                    JobStatusMessage]],
        worker_to_parent_queue: queue.Queue[Union[Except,
                                                  JobStatusMessage]],
        skip_errors: bool) -> LoopControl:
    """
    Mine changesets for inducing (presumed) errors.
    """
    try:
        changeset_mining_job = changeset_mining_job_queue.get_nowait()
    except Empty:
        pass
    else:
        result = mine_changesets_from_label_pair_star(changeset_mining_job)
        if not skip_errors and isinstance(result, Except):
            worker_to_parent_queue.put(result)
            return LoopControl.BREAK
        # If skip_errors is true and result is an Except, the
        # following will immediately return an empty list.
        error_instance_jobs = build_error_instance_creation_inputs(
            result,
            changeset_mining_job.repair_mining_logger)
        # inform parent of job start before queueing any subtasks
        worker_to_parent_queue.put(
            JobStatusMessage(
                JobID(
                    changeset_mining_job.label_a,
                    changeset_mining_job.label_b,
                    JobType.ERROR_INSTANCE),
                len(error_instance_jobs),
                JobStatus.QUEUED))
        worker_to_parent_queue.put(
            JobStatusMessage(
                JobID(
                    changeset_mining_job.label_a,
                    changeset_mining_job.label_b,
                    JobType.REPAIR_INSTANCE),
                len(error_instance_jobs),
                JobStatus.QUEUED))
        for error_instance_job in error_instance_jobs:
            error_instance_job_queue.put(error_instance_job)
        error_instance_job_queue.put(
            JobStatusMessage(
                JobID(
                    changeset_mining_job.label_a,
                    changeset_mining_job.label_b,
                    JobType.ERROR_INSTANCE),
                0,
                JobStatus.COMPLETED))
    return LoopControl.PASS


def mining_loop_worker(
        control_queue: queue.Queue[StopWorkSentinel],
        changeset_mining_job_queue: queue.Queue[ChangeSetMiningJob],
        error_instance_job_queue: queue.Queue[Union[ErrorInstanceJob,
                                                    JobStatusMessage]],
        repair_instance_job_queue: queue.Queue[RepairInstanceJob],
        worker_to_parent_queue: queue.Queue[Union[Except,
                                                  JobStatusMessage]],
        repair_instance_db_directory: Path,
        repair_miner: RepairMiner,
        skip_errors: bool) -> None:
    """
    Perform either error instance or repair instance mining.

    Parameters
    ----------
    control_queue : Queue
        Queue from which to retrieve control messages, if any
    changeset_mining_job_queue : Queue
        Queue from which to retrieve changeset mining jobs
    error_instance_job_queue : Queue
        Queue from which to retrieve error instance creation jobs
    repair_instance_job_queue : Queue
        Queue from which to retrieve repair instance creation jobs
    worker_to_parent_queue : Queue
        Queue for messages that need to be communicated back to the
        parent
    repair_instance_db_directory : Path
        Path to database file containing repair instance records
    repair_miner : RepairMiner
        Function used to mine repairs
    skip_errors : bool
        If true, allow repair mining to proceed even if an exception is
        encountered during error instance or repair mining. Other
        exceptions will not be ignored. If false, stop on exceptions in
        mining. By default, true.
    """
    # The order of the following blocks is important. We wish to keep
    # the size of the repair_instance_job_queue small so that we don't
    # run out of memory. Hence, our first step is to process any control
    # messages, then we check to see if any repair instance jobs are
    # available, do those, and only if none of those jobs are available
    # do we process error instance creation jobs and start filling up
    # the repair instance jobs queue again.
    while True:
        # Don't do anything until something is eligible to read.
        select.select(
            [
                control_queue._reader,  # type: ignore
                changeset_mining_job_queue._reader,  # type: ignore
                error_instance_job_queue._reader,  # type: ignore
                repair_instance_job_queue._reader  # type: ignore
            ],
            [],
            [])

        # #######################
        # Handle control messages
        # #######################

        try:
            control_message = control_queue.get_nowait()
        except Empty:
            pass
        else:
            if isinstance(control_message, StopWorkSentinel):
                break
        # ########################
        # Repair instance creation
        # ########################
        match _mine_repairs(repair_instance_job_queue,
                            worker_to_parent_queue,
                            skip_errors):
            case LoopControl.BREAK:
                break
            case LoopControl.CONTINUE:
                continue
            case LoopControl.PASS:
                pass
        # #######################
        # Error instance creation
        # #######################
        match _mine_errors(error_instance_job_queue,
                           repair_instance_job_queue,
                           worker_to_parent_queue,
                           repair_instance_db_directory,
                           repair_miner,
                           skip_errors):
            case LoopControl.BREAK:
                break
            case LoopControl.CONTINUE:
                continue
            case LoopControl.PASS:
                pass
        # #######################
        # Changeset mining
        # #######################
        match _mine_changesets(changeset_mining_job_queue,
                               error_instance_job_queue,
                               worker_to_parent_queue,
                               skip_errors):
            case LoopControl.BREAK:
                break
            case _:
                pass


def mining_loop_worker_star(args: tuple):
    """
    Bundle args and call mining_loop_worker.

    Parameters
    ----------
    args : tuple
        Bundled args for mining_loop_worker
    """
    mining_loop_worker(*args)


def filter_max_coq_version(
        cache_labels: Iterable[CacheObjectStatus]) -> List[CacheObjectStatus]:
    """
    Filter an iterable of cache labels by max Coq version.

    Parameters
    ----------
    cache_labels : Iterable[CacheObjectStatus]
        The iterable of cache labels to filter

    Returns
    -------
    List[CacheObjectStatus]
        The cache labels filtered by selecting only the highest Coq
        version for each project, commit, and status combination.
    """
    cache_label_dict_list = [asdict(label) for label in cache_labels]
    cache_label_df = pd.DataFrame(
        cache_label_dict_list,
        columns=["project",
                 "commit_hash",
                 "coq_version",
                 "status"])
    filtered_df = cache_label_df.groupby(["project",
                                          "commit_hash",
                                          "status"]).max().reset_index()
    output_label_list = [
        CacheObjectStatus(
            row['project'],
            row['commit_hash'],
            row['coq_version'],
            row['status']) for _,
        row in filtered_df.iterrows()
    ]
    return output_label_list


def prepare_label_pairs(
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
        project_commit_hashes = None
        if project_commit_hash_map is not None:
            project_commit_hashes = project_commit_hash_map[project]
        for cache_item_b in cache_items:
            if (project_commit_hash_map is None or project_commit_hashes is None
                    or cache_item_b.commit_hash in project_commit_hashes):
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
        project_commit_hashes = None
        if project_commit_hash_map is not None:
            project_commit_hashes = project_commit_hash_map[project]
        for cache_item_a in cache_items:
            if (project_commit_hash_map is None or project_commit_hashes is None
                    or cache_item_a.commit_hash in project_commit_hashes):
                _loop_over_second_label(
                    cache_item_a,
                    cache_items,
                    project_commit_hash_map,
                    cache_item_pairs,
                    consecutive_commit_hashes)

    with TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        cache = CoqProjectBuildCache(cache_root, cache_format_extension)
        project_list = cache.list_projects()
        if project_commit_hash_map is not None:
            project_list = [
                p for p in project_list if p in project_commit_hash_map
            ]
        all_cache_items = cache.list_status_success_only()
        max_version_cache_items = filter_max_coq_version(all_cache_items)
        cache_item_pairs: List[Tuple[CacheObjectStatus, CacheObjectStatus]] = []
        for project in project_list:
            cache_items = [
                t for t in max_version_cache_items if t.project == project
            ]
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


def _serial_work(
        cache_label_pairs: List[Tuple[CacheObjectStatus,
                                      CacheObjectStatus]],
        cache_args: Tuple[Path,
                          str],
        changeset_miner: ChangeSetMiner,
        repair_mining_logger: RepairMiningLogger,
        db_directory: Path,
        repair_miner: RepairMiner,
        skip_errors: bool,
        fast: bool):
    for label_a, label_b in tqdm(cache_label_pairs, desc="Mining commit pair"):
        changesets = mine_changesets_from_label_pair(
            label_a,
            label_b,
            *cache_args,
            changeset_miner,
            repair_mining_logger,
            fast)
        if isinstance(changesets, Except):
            raise RuntimeError(
                f"Exception: {changesets.exception}. "
                f"{changesets.trace}")
        (initial_state, repaired_state, commit_diff, changesets) = changesets
        for changeset in tqdm(changesets, desc="Repair instance mining"):
            result = build_error_instance(
                initial_state,
                repaired_state,
                commit_diff,
                changeset,
                repair_mining_logger)
            if isinstance(result, Except):
                if not skip_errors:
                    raise RuntimeError(
                        f"Exception: {result.exception}. {result.trace}")
                continue
            (error_instance, repaired_state, change_selection) = result
            result = build_repair_instance(
                error_instance,
                repaired_state,
                change_selection,
                db_directory,
                repair_miner,
                repair_mining_logger)
            if isinstance(result, Except) and not skip_errors:
                raise RuntimeError(
                    f"Exception: {result.exception}. {result.trace}")


def _process_parallel_worker_message(
    progress_bars: Dict[JobID,
                        tqdm],
    worker_msg: Union[JobStatusMessage,
                      Except[None]]) -> Union[bool,
                                              Except[None]]:
    """
    Process messages received from workers.

    Parameters
    ----------
    progress_bars : Dict[JobID, tqdm]
        A map from job IDs to progress bars.
    worker_msg : Union[JobStatusMessage, Except[None]]
        A message from a worker or a captured exception.

    Returns
    -------
    bool | Except[None]
        If a status message is received, then return True if the status
        indicates completion and False otherwise.
        If a captured exception is received, then return it.
        If an exception occurs during handling of the worker's message,
        then it is also captured and returned.
    """
    try:
        if isinstance(worker_msg, Except):
            return worker_msg
        elif worker_msg.status == JobStatus.COMPLETED:
            # a completion may arrive before each subtask
            return True
        elif worker_msg.status == JobStatus.QUEUED:
            assert worker_msg.job_id not in progress_bars, \
                f"This job has already been queued: {worker_msg.job_id}"
            progress_bars[worker_msg.job_id] = tqdm(
                total=worker_msg.job_size,
                desc=str(worker_msg.job_id),
                position=len(progress_bars))
        elif worker_msg.status == JobStatus.PROGRESSED:
            assert worker_msg.job_id in progress_bars, \
                f"This job has not been queued: {worker_msg.job_id}"
            pbar = progress_bars[worker_msg.job_id]
            pbar.update(worker_msg.job_size)
            if pbar.n == pbar.total:
                pbar.close()
    except Exception as e:
        return Except(None, e, format_exc(e))
    return False


def _parallel_work(
        cache_label_pairs: List[Tuple[CacheObjectStatus,
                                      CacheObjectStatus]],
        cache_args: Tuple[Path,
                          str],
        changeset_miner: ChangeSetMiner,
        repair_mining_logger: RepairMiningLogger,
        repair_instance_db_directory: Path,
        repair_miner: RepairMiner,
        max_workers: int,
        skip_errors: bool,
        fast: bool):
    changeset_mining_jobs = [
        ChangeSetMiningJob(
            label_a,
            label_b,
            *cache_args,
            changeset_miner,
            repair_mining_logger,
            fast) for label_a,
        label_b in cache_label_pairs
    ]
    control_queue: Queue[StopWorkSentinel] = Queue()
    changeset_mining_job_queue: Queue[ChangeSetMiningJob] = Queue()
    error_instance_job_queue: Queue[Union[ErrorInstanceJob,
                                          JobStatusMessage]] = Queue()
    repair_instance_job_queue: Queue[RepairInstanceJob] = Queue()
    worker_to_parent_queue: Queue[Union[Except, JobStatusMessage]] = Queue()
    proc_args = [
        control_queue,
        changeset_mining_job_queue,
        error_instance_job_queue,
        repair_instance_job_queue,
        worker_to_parent_queue,
        repair_instance_db_directory,
        repair_miner,
        skip_errors
    ]
    worker_processes: List[Process] = []
    # Start processes
    for _ in range(max_workers):
        worker_process = Process(target=mining_loop_worker, args=proc_args)
        worker_process.start()
        worker_processes.append(worker_process)
    # Load initial job queue
    for changeset_mining_job in changeset_mining_jobs:
        changeset_mining_job_queue.put(changeset_mining_job)
    expected_sentinels = len(changeset_mining_jobs)
    observed_sentinels = 0
    # Wait until work is finished or until we get a ctrl+c
    delayed_exception = None
    progress_bars: Dict[JobID,
                        tqdm] = {}
    try:
        while (observed_sentinels < expected_sentinels
               or any(pbar.n < pbar.total for pbar in progress_bars.values())):
            # Don't do anything until there's something to read.
            select.select(
                [worker_to_parent_queue._reader],  # type: ignore
                [],
                [])
            try:
                worker_msg = worker_to_parent_queue.get_nowait()
            except Empty:
                pass
            else:
                job_completed = _process_parallel_worker_message(
                    progress_bars,
                    worker_msg)
                if isinstance(job_completed, bool) and job_completed:
                    observed_sentinels += 1
                elif not isinstance(job_completed, bool):
                    assert isinstance(job_completed, Except)
                    delayed_exception = job_completed
    except KeyboardInterrupt:
        pass
    # ...then stop the workers and their processes
    for _ in range(len(worker_processes)):
        control_queue.put(StopWorkSentinel())
    for worker_process in worker_processes:
        worker_process.join()
    if delayed_exception is not None:
        raise RuntimeError(
            f"Delayed exception: {delayed_exception.exception}."
            f" {delayed_exception.trace}")


def repair_mining_loop(
        cache_root: Path,
        repair_instance_db_directory: Path,
        metadata_storage_file: Optional[Path] = None,
        cache_format_extension: str = "json",
        prepare_pairs: Optional[PreparePairsFunction] = None,
        repair_miner: Optional[RepairMiner] = None,
        changeset_miner: Optional[ChangeSetMiner] = None,
        serial: bool = False,
        max_workers: int = 1,
        project_commit_hash_map: Optional[Dict[str,
                                               Optional[List[str]]]] = None,
        logging_level: int = logging.DEBUG,
        skip_errors: bool = True,
        fast: bool = False):
    """
    Mine repair instances from the given build cache.

    Parameters
    ----------
    cache_root : Path
        Path to cache root to mine repair instances from
    repair_instance_db_directory : Path
        Path to directory for saving repair instances
    metadata_storage_file : Path or None, optional
        Path to metadata storage file to load for commit identification
    cache_format_extension : str, optional
        Extension of cache files, by default ``"json"``
    prepare_pairs : PreparePairsFunction, optional
        Function to prepare pairs of cache item labels to be used for
        repair instance mining, by default None
    repair_miner : RepairMiner, optional
        Function to mine repair instances given an error instance and a
        repaired state, by default None
    changeset_miner : Optional[ChangeSetMiner], optional
        Function to mine ChangeSelection objects, by default None
    serial : bool, optional
        Flag to control parallel execution, by default False. If True,
        use serial execution. If False, use parallel execution.
    max_workers : int or None, optional
        Maximum number of parallel workers to allow, by default None,
        which sets the value to min(32, number of cpus + 4)
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
    skip_errors : bool, optional
        If True, allow repair mining to proceed even if an exception is
        encountered during error instance or repair mining. Other
        exceptions will not be ignored. If False, stop on exceptions in
        mining. By default, True.
    fast : bool, optional
        If True, then accelerate mining by discarding extracted fields
        that are not required for alignment and identification of
        repairs, yielding only Git-based repair instances.
        Otherwise, keep all data and yield commit-data-based repair
        instances as well.
        By default, False.
    """
    os.makedirs(str(repair_instance_db_directory), exist_ok=True)
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
    with RepairMiningLoggerServer() as logging_server:
        repair_mining_logger = logging_server.Client(
            repair_instance_db_directory,
            logging_level,
        )
        cache_args = (cache_root, cache_format_extension)
        cache_label_pairs = prepare_pairs(
            *cache_args,
            metadata_storage,
            project_commit_hash_map)
        # ##############################################################
        # Serial processing
        # ##############################################################
        if serial:
            _serial_work(
                cache_label_pairs,
                cache_args,
                changeset_miner,
                repair_mining_logger,
                repair_instance_db_directory,
                repair_miner,
                skip_errors,
                fast)
        # ##############################################################
        # Parallel processing
        # ##############################################################
        else:
            _parallel_work(
                cache_label_pairs,
                cache_args,
                changeset_miner,
                repair_mining_logger,
                repair_instance_db_directory,
                repair_miner,
                max_workers,
                skip_errors,
                fast)
