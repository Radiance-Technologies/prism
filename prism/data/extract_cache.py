"""
Module for storing cache extraction functions.
"""
import multiprocessing as mp
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Type,
    Union,
)

import tqdm
from seutil import io

from prism.data.build_cache import (
    CoqProjectBuildCacheClient,
    CoqProjectBuildCacheServer,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandData,
    VernacDict,
    create_cpbcs_qs,
)
from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.util import get_project_func
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.util import ParserUtils
from prism.project.base import SEM, Project
from prism.project.exception import ProjectBuildError
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import (
    ChangedCoqCommitIterator,
    CommitIterator,
    ProjectRepo,
)
from prism.util.opam.version import Version
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager

from ..language.gallina.analyze import SexpAnalyzer


def extract_vernac_commands(
        project: ProjectRepo,
        serapi_options: Optional[str] = None) -> VernacDict:
    """
    Compile vernac commands from a project into a dict.

    Parameters
    ----------
    project : ProjectRepo
        The project from which to extract the vernac commands
    """
    if serapi_options is None:
        serapi_options = project.serapi_options
    command_data = {}
    for filename in project.get_file_list():
        file_commands: List[VernacCommandData] = command_data.setdefault(
            filename,
            list())
        with pushd(project.dir_abspath):
            with SerAPI(project.serapi_options) as serapi:
                for sentence in project.get_sentences(
                        filename,
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False):
                    location = sentence.location
                    sentence = sentence.text
                    _, _, sexp = serapi.execute(sentence, True)
                    if SexpAnalyzer.is_ltac(sexp):
                        # This is where we would handle proofs
                        ...
                    else:
                        command_type, identifier = \
                            ParserUtils.extract_identifier(sentence)
                        file_commands.append(
                            VernacCommandData(
                                identifier,
                                command_type,
                                None,
                                sentence,
                                sexp,
                                location))
    return command_data


def extract_cache(
        build_cache_client: CoqProjectBuildCacheClient,
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: Optional[str] = None,
        recache: Optional[Callable[
            [CoqProjectBuildCacheServer,
             ProjectRepo,
             str,
             str],
            bool]] = None,
        block: bool = False) -> None:
    r"""
    Extract data from project commit and insert into `build_cache`.

    The cache is implemented as a file-and-directory-based
    repository structure (`CoqProjectBuildCache`) that provides
    storage of artifacts and concurrent access for parallel
    processes through the operating system's own file system.
    Directories identify projects and commits with a separate cache
    file per build environment (i.e., Coq version). The presence or
    absence of a cache file within the structure indicates whether
    the commit has been cached yet. The cache files themselves
    contain two key pieces of information (reflected in
    `ProjectCommitData`): the metadata for the commit and a map from
    Coq file paths in the project to sets of per-sentence build
    artifacts (represented by `VernacCommandData`).

    This function does not return any cache extracted. Instead, it
    modifies on-disk build cache by inserting any previously unseen
    cache artifacts.

    Parameters
    ----------
    build_cache_client : CoqProjectBuildCacheClient
        The client that can insert the build artifacts into the on-disk
        build cache.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command
        extraction for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, \
                    str], bool]
            or None, optional
        A function that for an existing entry in the cache returns
        whether it should be reprocessed or not.
    block : bool, optional
        Whether to use blocking cache writes, by default False

    See Also
    --------
    prism.data.build_cache.CoqProjectBuildCache
    prism.data.build_cache.ProjectCommitData
    prism.data.build_cache.VernacCommandData
    """
    if coq_version is None:
        coq_version = project.metadata.coq_version
    if ((project.name,
         commit_sha,
         coq_version) not in build_cache_client
            or (recache is not None and recache(build_cache_client,
                                                project,
                                                commit_sha,
                                                coq_version))):
        extract_cache_new(
            build_cache_client,
            switch_manager,
            project,
            commit_sha,
            process_project,
            coq_version,
            block)


def extract_cache_new(
        build_cache_client: CoqProjectBuildCacheClient,
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: str,
        block: bool):
    """
    Extract a new cache and insert it into the build cache.

    Parameters
    ----------
    build_cache_client : CoqProjectBuildCacheClient
        The client that can communicate the build cache to be written to
        the build cache server
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command
        extraction for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    block : bool
        Whether to use blocking cache writes
    """
    project.git.checkout(commit_sha)
    # get a switch
    dependency_formula = project.get_dependency_formula(coq_version)
    original_switch = project.opam_switch
    project.opam_switch = switch_manager.get_switch(
        dependency_formula,
        variables={
            'build': True,
            'post': True,
            'dev': True
        })
    # process the commit
    metadata = project.metadata
    try:
        build_result = project.build()
    except ProjectBuildError as pbe:
        build_result = (pbe.return_code, pbe.stdout, pbe.stderr)
        command_data = process_project(project)
    else:
        command_data = extract_vernac_commands(project, metadata.serapi_options)
    data = ProjectCommitData(
        metadata,
        command_data,
        ProjectBuildEnvironment(project.opam_switch.export()),
        ProjectBuildResult(*build_result))
    build_cache_client.insert(data, block)
    # release the switch
    switch_manager.release_switch(project.opam_switch)
    project.opam_switch = original_switch


def cache_extract_commit_iterator(iterator: CommitIterator):
    """
    Provide default commit iterator for cache extraction.
    """
    for item in iterator:
        yield item.hexsha


class CacheExtractor:
    """
    Class for managing a broad Coq project cache extraction process.
    """

    _avail_cache_kwargs = ["fmt_ext"]
    _avail_mds_kwargs = ["fmt"]

    def __init__(
            self,
            cache_dir: str,
            metadata_storage_file: str,
            swim: SwitchManager,
            default_commits_path: str,
            commit_iterator_cls: Type[
                CommitIterator] = ChangedCoqCommitIterator,
            coq_version_iterator: Optional[Callable[[Project,
                                                     str],
                                                    Iterable[Union[
                                                        str,
                                                        Version]]]] = None,
            process_project: Optional[Callable[[ProjectRepo],
                                               VernacDict]] = None,
            **kwargs):
        self.cache_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_cache_kwargs
        }
        mds_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_mds_kwargs
        }
        self.cache_dir = cache_dir
        self.swim = swim
        self.md_storage = MetadataStorage.load(
            metadata_storage_file,
            **mds_kwargs)
        self.md_storage_file = metadata_storage_file
        self.commit_iterator_cls = commit_iterator_cls
        self.default_commits_path = default_commits_path
        self.default_commits: Dict[str,
                                   List[str]] = io.load(
                                       self.default_commits_path,
                                       clz=dict)

        if coq_version_iterator is None:
            self.coq_version_iterator = self._default_coq_version_iterator
        else:
            self.coq_version_iterator = coq_version_iterator

        if process_project is None:
            self.process_project = self._default_process_project
        else:
            self.process_project = process_project

    @staticmethod
    def _commit_iterator_func(
            project: ProjectRepo,
            default_commits: Dict[str,
                                  List[str]],
            commit_iterator_cls: Type[CommitIterator]) -> Iterator[str]:
        for remote in project.remotes:
            remote.fetch()
        starting_commit_sha = default_commits[project.metadata.project_name][0]
        return cache_extract_commit_iterator(
            commit_iterator_cls(project,
                                starting_commit_sha))

    def get_commit_iterator_func(
            self) -> Callable[[ProjectRepo],
                              Iterator[str]]:
        """
        Return a commit iterator function.

        Returns
        -------
        Callable[[ProjectRepo], Iterator[str]]
            The chosen commit iterator function
        """
        return partial(
            CacheExtractor._commit_iterator_func,
            default_commits=self.default_commits,
            commit_iterator_cls=self.commit_iterator_cls)

    @staticmethod
    def extract_cache_func(
        project: ProjectRepo,
        commit_sha: str,
        _result: None,
        build_cache_client_map: Dict[str,
                                     CoqProjectBuildCacheClient],
        switch_manager: SwitchManager,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version_iterator: Callable[[Project,
                                        str],
                                       Iterable[Union[str,
                                                      Version]]]):
        """
        Extract cache.

        Parameters
        ----------
        project : ProjectRepo
            The project to extract cache from
        commit_sha : str
            The commit to extract cache from
        _result : None
            Left empty for compatibility with `ProjectCommitMapper`
        build_cache_client_map : Dict[str, CoqProjectbuildCacheClient]
            A mapping from project name to build cache client, used to
            write extracted cache to disk
        switch_manager : SwitchManager
            A switch manager to use during extraction
        process_project : Callable[[Project], VernacDict]
            A function that does a best-effort cache extraction when the
            project does not build
        coq_version_iterator : Callable[[Project, str],
                                        Iterable[Union[str, Version]]]
            A function that returns an iterable over allowable coq
            versions
        """
        for coq_version in tqdm.tqdm(coq_version_iterator(project,
                                                          commit_sha),
                                     desc="Coq version"):
            extract_cache(
                build_cache_client_map[project.name],
                switch_manager,
                project,
                commit_sha,
                process_project,
                str(coq_version),
                CacheExtractor.recache)

    def get_extract_cache_func(
            self) -> Callable[[ProjectRepo,
                               str,
                               None],
                              None]:
        """
        Return the cache extraction function for the commit mapper.

        Returns
        -------
        Callable[[ProjectRepo, str, None], None]
            The extraction function to be mapped
        """
        return partial(
            CacheExtractor.extract_cache_func,
            build_cache_client_map=self.cache_clients,
            switch_manager=self.swim,
            process_project=self.process_project,
            coq_version_iterator=self.coq_version_iterator)

    def _default_coq_version_iterator(self, *args, **kwargs):
        return ["8.10.2"]

    def _default_process_project(self, *args, **kwargs) -> VernacDict:
        return dict()

    @staticmethod
    def recache(
            build_cache: CoqProjectBuildCacheServer,
            project: ProjectRepo,
            commit_sha: str,
            coq_version: str) -> bool:
        """
        Provide a placeholder function for now.
        """
        return False

    def run(
            self,
            root_path: str,
            log_dir: Optional[str] = None,
            updated_md_storage_file: Optional[str] = None,
            extract_nprocs: int = 8,
            force_serial: bool = False,
            n_build_workers: int = 1) -> None:
        """
        Build all projects at `root_path` and save updated metadata.

        Parameters
        ----------
        root_path : PathLike
            The root directory containing each project's directory.
            The project directories do not need to already exist.
        log_dir : str or None, optional
            Directory to store log file(s) in, by default the directory
            that the metadata storage file is loaded from
        updated_md_storage_file : str or None, optional
            File to save the updated metadata storage file to, by
            default the original file's parent directory /
            "updated_metadata.yml"
        extract_nprocs : int, optional
            Number of workers to allow for cache extraction, by default
            8
        """
        if log_dir is None:
            log_dir = Path(self.md_storage_file).parent
        if updated_md_storage_file is None:
            updated_md_storage_file = (
                Path(self.md_storage_file).parent / "updated_metadata.yml")
        # Generate list of projects
        projects = list(
            tqdm.tqdm(
                Pool(20).imap(
                    get_project_func(
                        root_path,
                        self.md_storage,
                        n_build_workers),
                    self.md_storage.projects),
                desc="Initializing Project instances",
                total=len(self.md_storage.projects)))
        if force_serial:
            client_keys = None
            client_to_server_q = None
            server_to_client_q_dict = None
        else:
            client_keys = [project.name for project in projects]
            manager = mp.Manager()
            client_to_server_q, server_to_client_q_dict = create_cpbcs_qs(
                manager,
                client_keys)
        with CoqProjectBuildCacheServer(self.cache_dir,
                                        client_keys,
                                        client_to_server_q,
                                        server_to_client_q_dict,
                                        **self.cache_kwargs) as cache_server:
            if force_serial:
                self.cache_clients = {
                    project.name: cache_server for project in projects
                }
            else:
                self.cache_clients = {
                    project.name: CoqProjectBuildCacheClient(
                        cache_server.client_to_server,
                        cache_server.server_to_client_dict[project.name],
                        project.name) for project in projects
                }
            # Create commit mapper
            project_looper = ProjectCommitUpdateMapper[None](
                projects,
                self.get_commit_iterator_func(),
                self.get_extract_cache_func(),
                "Extracting cache",
                terminate_on_except=False)
            # Extract cache in parallel
            results, metadata_storage = project_looper.update_map(
                extract_nprocs,
                force_serial)
            # report errors
            with open(log_dir) as f:
                for p, result in results.items():
                    if isinstance(result, Except):
                        print(
                            f"{type(result.exception)} encountered in project {p}:"
                        )
                        print(result.trace)
                        f.write(
                            '\n'.join(
                                [
                                    "##########################################"
                                    "#########",
                                    f"{type(result.exception)} encountered in"
                                    f" project {p}:",
                                    result.trace
                                ]))
            # update metadata
            metadata_storage.dump(metadata_storage, updated_md_storage_file)
            print("Done")
