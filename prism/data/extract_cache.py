"""
Module for storing cache extraction functions.
"""
import logging
import traceback
from functools import partial, reduce
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Union

import tqdm
from seutil import io

from prism.data.build_cache import (
    CoqProjectBuildCache,
    ProjectBuildEnvironment,
    ProjectBuildResult,
    ProjectCommitData,
    VernacCommandData,
    VernacDict,
)
from prism.data.commit_map import Except, ProjectCommitUpdateMapper
from prism.data.setup import create_default_switches
from prism.interface.coq.serapi import SerAPI
from prism.language.heuristic.util import ParserUtils
from prism.project.base import SEM, Project, SentenceExtractionMethod
from prism.project.exception import ProjectBuildError
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.util.opam import OpamSwitch, PackageFormula
from prism.util.opam.formula import LogicalPF, LogOp
from prism.util.opam.version import Version
from prism.util.radpytools.os import pushd
from prism.util.swim import SwitchManager
from prism.util.swim.auto import AutoSwitchManager

from ..language.gallina.analyze import SexpAnalyzer, SexpInfo


def get_dependency_formula(
        opam_dependencies: List[str],
        ocaml_version: Optional[Union[str,
                                      Version]],
        coq_version: str) -> PackageFormula:
    """
    Get the dependency formula for the given constraints.

    This formula can then be used to retrieve an appropriate switch.
    """
    formula = []
    formula.append(PackageFormula.parse(f'"coq.{coq_version}"'))
    formula.append(PackageFormula.parse('"coq-serapi"'))
    if ocaml_version is not None:
        formula.append(PackageFormula.parse(f'"ocaml.{ocaml_version}"'))
    for dependency in opam_dependencies:
        formula.append(PackageFormula.parse(dependency))
    formula = reduce(
        lambda l,
        r: LogicalPF(l,
                     LogOp.AND,
                     r),
        formula[1 :],
        formula[0])
    return formula


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
                for sentence, location in zip(*project.extract_sentences(
                        project.get_file(filename),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
                        glom_proofs=False)):
                    sentence: str
                    location: SexpInfo.Loc
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
    build_cache: CoqProjectBuildCache,
    switch_manager: SwitchManager,
    project: ProjectRepo,
    commit_sha: str,
    process_project: Callable[[Project],
                              VernacDict],
    coq_version: Optional[str] = None,
    recache: Optional[Callable[[CoqProjectBuildCache,
                                ProjectRepo,
                                str,
                                str],
                               bool]] = None
) -> None:
    r"""
    Extract data from a project commit and insert it into `build_cache`.

    The cache is implemented as a file-and-directory-based repository
    structure (`CoqProjectBuildCache`) that provides storage of
    artifacts and concurrent access for parallel processes through the
    operating system's own file system. Directories identify projects
    and commits with a separate cache file per build environment (i.e.,
    Coq version). The presence or absence of a cache file within the
    structure indicates whether the commit has been cached yet. The
    cache files themselves contain two key pieces of information
    (reflected in `ProjectCommitData`): the metadata for the commit and
    a map from Coq file paths in the project to sets of per-sentence
    build artifacts (represented by `VernacCommandData`).

    This function does not return any cache extracted. Instead, it
    modifies on-disk build cache by inserting any previously unseen
    cache artifacts.

    Parameters
    ----------
    build_cache : CoqProjectBuildCache
        The build cache in which to insert the build artifacts.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command extraction
        for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    recache : Callable[[CoqProjectBuildCache, ProjectRepo, str, str], \
                       bool]
              or None, optional
        A function that for an existing entry in the cache returns
        whether it should be reprocessed or not.

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
         coq_version) not in build_cache
            or (recache is not None and recache(build_cache,
                                                project,
                                                commit_sha,
                                                coq_version))):
        extract_cache_new(
            build_cache,
            switch_manager,
            project,
            commit_sha,
            process_project,
            coq_version)


def extract_cache_new(
        build_cache: CoqProjectBuildCache,
        switch_manager: SwitchManager,
        project: ProjectRepo,
        commit_sha: str,
        process_project: Callable[[Project],
                                  VernacDict],
        coq_version: str):
    """
    Extract a new cache and insert it into the build cache.

    Parameters
    ----------
    build_cache : CoqProjectBuildCache
        The build cache in which to insert the build artifacts.
    switch_manager : SwitchManager
        A source of switches in which to process the project.
    project : ProjectRepo
        The project from which to extract data.
    commit_sha : str
        The commit whose data should be extracted.
    process_project : Callable[[Project], VernacDict]
        Function that provides fallback vernacular command extraction
        for projects that do not build.
    coq_version : str or None, optional
        The version of Coq in which to build the project, by default
        None.
    """
    project.git.checkout(commit_sha)
    # get a switch
    dependency_formula = get_dependency_formula(
        project.opam_dependencies,  # infers dependencies as side-effect
        project.ocaml_version,
        coq_version)
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
    build_cache.insert(data)
    # release the switch
    switch_manager.release_switch(project.opam_switch)
    project.opam_switch = original_switch


class CacheExtractor:
    """
    Class for managing a broad Coq project cache extraction process.
    """

    _avail_cache_kwargs = ["fmt_ext", "num_workers"]
    _avail_swim_kwargs = ["variables"]
    _avail_mds_kwargs = ["fmt"]

    def __init__(
            self,
            cache_dir: str,
            metadata_storage_file: str,
            initial_switches: Optional[Iterable[OpamSwitch]] = None,
            **kwargs):
        cache_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_cache_kwargs
        }
        swim_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_swim_kwargs
        }
        mds_kwargs = {
            k: v for k,
            v in kwargs.items() if k in self._avail_mds_kwargs
        }
        self.cache = CoqProjectBuildCache(cache_dir, **cache_kwargs)
        self.swim = SwitchManager(initial_switches, **swim_kwargs)
        self.md_storage = MetadataStorage.load(
            metadata_storage_file,
            **mds_kwargs)

    def get_project(self, root_path: str, project_name: str) -> ProjectRepo:
        """
        Get the identified project's `ProjectRepo` representation.
        """
        repo_path = Path(root_path) / project_name
        return ProjectRepo(
            repo_path,
            self.md_storage,
            sentence_extraction_method=SentenceExtractionMethod.SERAPI)

    def get_project_func(  # noqa: D103, D102
            self,
            root_path: str) -> Callable[[str],
                                        ProjectRepo]:
        from seutil import io
        io.dump()
        return partial(CacheExtractor.get_project, root_path, self.md_storage)

    @staticmethod
    def get_commit_iterator(
            default_commits: Dict[str,
                                  List[str]],
            project: ProjectRepo) -> Set[str]:
        """
        Get an iterator over a project's default commits.
        """
        return default_commits[project.metadata.project_name]

    @staticmethod
    def get_commit_iterator_func(  # noqa: D103, D102
        default_commits: Dict[str,
                              List[str]]) -> Callable[[ProjectRepo],
                                                      List[str]]:
        return partial(CacheExtractor.get_commit_iterator, default_commits)

    @staticmethod
    def process_commit(
            switch_manager: SwitchManager,
            project: ProjectRepo,
            commit: str,
            results: None) -> None:
        """
        Build the project at the given commit.
        """
        try:
            project.git.checkout(commit)
            coq_version = project.metadata_storage.get_project_coq_versions(
                project.name,
                project.remote_url,
                project.commit_sha)
            try:
                coq_version = coq_version.pop()
            except KeyError:
                coq_version = '8.10.2'
            print(f'Choosing "coq.{coq_version}" for {project.name}')
            # get a switch
            project.infer_opam_dependencies()  # force inference
            dependency_formula = get_dependency_formula(
                project.opam_dependencies,
                project.ocaml_version,
                coq_version)
            original_switch = project.opam_switch
            project.opam_switch = switch_manager.get_switch(
                dependency_formula,
                variables={
                    'build': True,
                    'post': True,
                    'dev': True
                })
            # process the commit
            _ = project.build()
        except Exception:
            logging.debug(
                f"Skipping build for {project.metadata.project_name}:"
                f"{traceback.format_exc()}")
            raise
        finally:
            switch_manager.release_switch(project.opam_switch)
            project.opam_switch = original_switch

    @staticmethod
    def get_process_commit_func(  # noqa: D103, D102
        switch_manager: SwitchManager) -> Callable[[ProjectRepo,
                                                    str,
                                                    None],
                                                   None]:
        return partial(CacheExtractor.process_commit, switch_manager)

    @staticmethod
    def main(
            root_path: str,
            storage_path: str,
            default_commits_path: str) -> None:
        """
        Build all projects at `root_path` and save updated metadata.

        Parameters
        ----------
        root_path : PathLike
            The root directory containing each project's directory.
            The project directories do not need to already exist.
        storage_path : PathLike
            The path to a file containing metadata for each project to
            be built at `root_path`.
        default_commits_path : PathLike
            The path to a file identifying the default commits for each
            project in the storage.
        """
        # Initialize from arguments
        metadata_storage = MetadataStorage.load(storage_path)
        default_commits: Dict[str,
                              List[str]] = io.load(
                                  default_commits_path,
                                  clz=dict)
        create_default_switches(7)
        switch_manager = AutoSwitchManager()
        # Generate list of projects
        projects = list(
            tqdm.tqdm(
                Pool(20).imap(
                    CacheExtractor.get_project_func(
                        root_path,
                        metadata_storage),
                    metadata_storage.projects),
                desc="Initializing Project instances",
                total=len(metadata_storage.projects)))
        # Create commit mapper
        project_looper = ProjectCommitUpdateMapper(
            projects,
            CacheExtractor.get_commit_iterator_func(default_commits),
            CacheExtractor.get_process_commit_func(switch_manager),
            "Building projects",
            terminate_on_except=False)
        # Build projects in parallel
        results, metadata_storage = project_looper.update_map(30)
        storage_dir = Path(storage_path).parent
        # report errors
        with open(storage_dir / "build_error_log.txt") as f:
            for p, result in results.items():
                if isinstance(result, Except):
                    print(
                        f"{type(result.exception)} encountered in project {p}:")
                    print(result.trace)
                    f.write(
                        '\n'.join(
                            [
                                "###################################################",
                                f"{type(result.exception)} encountered in project {p}:",
                                result.trace
                            ]))
        # update metadata
        metadata_storage.dump(
            metadata_storage,
            storage_dir / "updated_metadata.yaml")
        print("Done")
