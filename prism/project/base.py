"""
Module providing Coq project class representations.
"""

import glob
import logging
import os
import pathlib
import random
import re
import typing
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import fields
from enum import Enum, auto
from functools import partialmethod, reduce
from itertools import chain
from pathlib import Path
from subprocess import CalledProcessError
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import prism.util.build_tools.opamdep as opamdep
from prism.data.document import CoqDocument
from prism.interface.coq.iqr import IQR
from prism.interface.coq.options import SerAPIOptions
from prism.interface.coq.re_patterns import QUALIFIED_IDENT_PATTERN
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import (
    CoqComment,
    CoqSentence,
    HeuristicParser,
    SerAPIParser,
)
from prism.project.exception import (
    MissingMetadataError,
    ProjectBuildError,
    ProjectCommandError,
)
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.strace import strace_build
from prism.util.bash import escape
from prism.util.build_tools.coqdep import (
    make_dependency_graph,
    order_dependencies,
)
from prism.util.logging import default_log_level
from prism.util.opam import (
    AssignedVariables,
    OpamSwitch,
    PackageFormula,
    Version,
    major_minor_version_bound,
)
from prism.util.opam.formula import LogicalPF, LogOp
from prism.util.path import get_relative_path
from prism.util.radpytools import PathLike
from prism.util.radpytools.os import pushd
from prism.util.re import regex_from_options
from prism.util.swim import SwitchManager

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(default_log_level())

_T = TypeVar('_T')


class SentenceExtractionMethod(Enum):
    """
    Enum for available sentence extraction methods.

    Attributes
    ----------
    SERAPI
        Use serapi to extract sentences
    HEURISTIC
        Use custom heuristic method to extract sentences
    """

    SERAPI = auto()
    HEURISTIC = auto()

    def parser(self) -> Union[Type[HeuristicParser], Type[SerAPIParser]]:
        """
        Return the appropriate parser for the SEM.
        """
        method_enum = SentenceExtractionMethod(self.value)
        if method_enum is SentenceExtractionMethod.SERAPI:
            return SerAPIParser
        elif method_enum is SentenceExtractionMethod.HEURISTIC:
            return HeuristicParser
        else:
            raise ValueError(
                f"Extraction method {method_enum} doesn't have specified parser"
            )


SEM = SentenceExtractionMethod


class MetadataArgs(NamedTuple):
    """
    Arguments that identify metadata for an implicit project.
    """

    project_url: Optional[str]
    commit_sha: Optional[str]
    coq_version: Optional[str]
    ocaml_version: Optional[str]


class Project(ABC):
    """
    Abstract base class for representing a Coq project.

    Parameters
    ----------
    dir_abspath : str
        The absolute path to the project's root directory.
    metadata_storage : MetadataStorage
        MetadataStorage for referencing all possible metadata
        configurations for the project.
    opam_switch : OpamSwitch
        Object for tracking OpamSwitch relevant for this project
    sentence_extraction_method : SentenceExtractionMethod
        The method by which sentences are extracted.
    project_logger : logging.Logger
        Logger used to send log messages.
    """

    _missing_dependency_pattern = regex_from_options(
        [
            s.replace(" ",
                      r"\s+")
            for s in [
                rf"[Cc]annot find a physical path bound to logical path "
                rf"(?P<logical>{QUALIFIED_IDENT_PATTERN.pattern})",
                r"[Uu]nable to locate library "
                rf"(?P<suffix>{QUALIFIED_IDENT_PATTERN.pattern}) "
                rf"with prefix (?P<prefix>{QUALIFIED_IDENT_PATTERN.pattern})",
                rf"[Cc]annot load (?P<unbound>{QUALIFIED_IDENT_PATTERN.pattern}): "
                "no physical path bound to",
                r"[Cc]annot find library "
                rf"(?P<library>{QUALIFIED_IDENT_PATTERN.pattern})"
            ]
        ],
        False,
        False)

    coq_library_exts = ["*.vio", "*.vo", "*.vos", "*.vok"]
    """
    A list of possible Coq library file extensions.
    """

    def __init__(
            self,
            dir_abspath: PathLike,
            metadata_storage: MetadataStorage,
            opam_switch: Optional[OpamSwitch] = None,
            sentence_extraction_method: SEM = SentenceExtractionMethod.SERAPI,
            num_cores: Optional[int] = None,
            switch_manager: Optional[SwitchManager] = None,
            project_logger: Optional[logging.Logger] = None):
        """
        Initialize Project object.
        """
        self.dir_abspath = dir_abspath
        """
        The absolute path to the project's root directory.
        """
        self.metadata_storage = metadata_storage
        """
        Project metadata containing information such as project name
        and commands.
        """
        self.sentence_extraction_method = sentence_extraction_method
        """
        The method by which sentences are extracted.
        """
        try:
            name = self.name.replace('.', '_')
        except NotImplementedError:
            name = 'project'
        self.logger = (project_logger or logger).getChild(f"{name}")
        if opam_switch is not None:
            self.opam_switch = opam_switch
        else:
            self.opam_switch = OpamSwitch()
        self.num_cores = num_cores
        self._last_metadata_args: Optional[MetadataArgs] = None
        self._metadata: Optional[ProjectMetadata] = None
        self.switch_manager = switch_manager

    @property
    def build_cmd(self) -> List[str]:
        """
        Return the list of commands that build the project.
        """
        cmd_list = self.metadata.build_cmd
        for i in range(len(cmd_list)):
            if 'make' in cmd_list[i] and self.num_cores is not None:
                cmd_list[i] = cmd_list[i] + " -j{0}".format(self.num_cores)
        return cmd_list

    @property
    def clean_cmd(self) -> List[str]:
        """
        Return the list of commands that clean project build artifacts.
        """
        return self.metadata.clean_cmd

    @property
    def coq_options(self) -> Optional[str]:
        """
        Get the Coq options for compiling this project's files.

        If None, then the Coq options have not yet been determined
        and will be inferred automatically the next time the project is
        built.

        Returns
        -------
        Optional[str]
            The command-line options for invoking Coq tools, e.g.,
            ``f"coqc {coq_options} file.v"``.
        """
        if self.serapi_options is not None:
            coq_options = self.serapi_options.as_coq_args()
        else:
            coq_options = None
        return coq_options

    @property
    def coq_version(self) -> str:
        """
        Get the version of OCaml installed in the project's switch.
        """
        assert self._coq_version is not None, "Coq must be installed"
        return self._coq_version

    @property
    def ignore_path_regex(self) -> re.Pattern:
        """
        Get the regular expression that matches Coq filepaths to ignore.
        """
        return regex_from_options(self.metadata.ignore_path_regex, True, True)

    @property
    def install_cmd(self) -> List[str]:
        """
        Return the list of commands that install the project.
        """
        return self.metadata.install_cmd

    @property
    def iqr_flags(self) -> Optional[IQR]:
        """
        The IQR flags given to the Coq when compiling this project.
        """
        iqr = None
        if self.serapi_options is not None:
            iqr = self.serapi_options.iqr
            logger = self.logger.getChild('iqr_flags')
            logger.debug(f"{iqr}")
        return iqr

    @property
    def is_metadata_stale(self) -> bool:
        """
        Return whether the current metadata needs to be updated.
        """
        return self.metadata_args != self._last_metadata_args

    @property
    def metadata(self) -> ProjectMetadata:
        """
        Get up-to-date metadata for the project.
        """
        if self.is_metadata_stale:
            self._metadata = self._get_fresh_metadata()
        assert self._metadata is not None
        return self._metadata

    @property
    @abstractmethod
    def metadata_args(self) -> MetadataArgs:
        """
        Get arguments that can retrieve the metadata from storage.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the name of the project.
        """
        ...

    @property
    def ocaml_version(self) -> Optional[str]:
        """
        Get the version of OCaml installed in the project's switch.
        """
        return self._ocaml_version

    @property
    def opam_dependencies(self) -> List[str]:
        """
        Get the OPAM-installable dependencies of this project.

        Returns
        -------
        List[str]
            A list of serialized `PackageFormula` that must each be
            satisfied by the project's `OpamSwitch` prior to building.
        """
        opam_deps = self.metadata.opam_dependencies
        if opam_deps is None:
            opam_deps = self.infer_opam_dependencies()
        return opam_deps

    @property
    def opam_switch(self) -> OpamSwitch:
        """
        Get the project's switch, which entails the build environment.
        """
        return self._opam_switch

    @opam_switch.setter
    def opam_switch(self, switch: OpamSwitch) -> None:
        """
        Set the project's switch and update cached version data.
        """
        self._opam_switch = switch
        self._coq_version = switch.get_installed_version("coq")
        self._ocaml_version = switch.get_installed_version("ocaml")
        logger = self.logger.getChild('opam_switch.setter')
        logger.debug(
            "Setting switch to "
            f" {switch.name}(coq={self._coq_version}, ocaml={self._ocaml_version})"
        )

    @property
    @abstractmethod
    def path(self) -> Path:
        """
        Get the path to the project's root directory.
        """
        pass

    @property
    def serapi_options(self) -> Optional[SerAPIOptions]:
        """
        Get the SerAPI options for parsing this project's files.

        If None, then the SerAPI options have not yet been determined
        and will be inferred automatically the next time the project is
        built.

        Returns
        -------
        Optional[str]
            The command-line options for invoking SerAPI tools, e.g.,
            ``f"sertop {serapi_options.get_sertop_args()}"``.
        """
        return self.metadata.serapi_options

    @property
    def size_bytes(self) -> int:
        """
        Get size in bytes of working directory.

        A measure of the total space on disk occupied by files in the
        project directory in bytes. This size should exclude the
        contents of any .git directories.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.path).glob('**/*')
            if f.is_file()) - sum(
                f.stat().st_size
                for f in pathlib.Path(self.path).glob('**/.git/**/*')
                if f.is_file())

    def _check_serapi_option_health_pre_build(self) -> bool:
        """
        Check the integrity of SerAPI options before building.

        Verify `serapi_options` exists and corresponds to existing
        paths.
        """
        logger = self.logger.getChild('_check_serapi_option_health_pre_build')
        if self.serapi_options is None:
            logger.debug("No serapi options")
            return False
        # Check if current IQR flags map to current directories.
        for physical_path in self._iqr_bound_directories(False):
            if not physical_path.exists():
                logger.debug(
                    f"Missing physical path for iqr flag: {physical_path}")
                return False
        return True

    def _check_serapi_option_health_post_build(self) -> bool:
        """
        Check the integrity of SerAPI options after building.

        Verify two conditions are met for post-build `serapi_options`:

        1. QR physical paths contain *.vo files;
        2. All *.vo files' paths start with a physical path in
           serapi_options.
        """
        logger = self.logger.getChild('_check_serapi_option_health_post_build')
        full_q_paths = list(
            self._iqr_bound_directories(
                False,
                return_I=False,
                return_Q=True,
                return_R=False))
        full_r_paths = list(
            self._iqr_bound_directories(
                False,
                return_I=False,
                return_Q=False,
                return_R=True))
        for full_path in full_q_paths:
            if not glob.glob(f"{full_path}/*.vo", recursive=False):
                logger.debug(f"Q path has no *.vo files: {full_path}")
                return False
        for full_path in full_r_paths:
            if not glob.glob(f"{full_path}/**/*.vo", recursive=True):
                logger.debug(f"R path has no *.vo files: {full_path}")
                return False
        for vo_file in glob.glob(f"{self.path}/**/*.vo", recursive=True):
            vo_file_path = Path(vo_file)
            if full_r_paths and not any(full_path in vo_file_path.parents
                                        for full_path in full_r_paths):
                logger.debug(
                    f"A .vo file ({vo_file_path}): has no matching R path")
                return False
            if full_q_paths and not any(full_path == vo_file_path.parent
                                        for full_path in full_q_paths):
                logger.debug(
                    f"A .vo file ({vo_file_path}): has no matching Q path")
                return False
        return True

    def _clean(self) -> None:
        """
        Remove all compiled Coq library (object) files.
        """
        for ext in self.coq_library_exts:
            for lib in pathlib.Path(self.path).rglob(ext):
                lib.unlink()

    def _get_fresh_metadata(self) -> ProjectMetadata:
        """
        Get refreshed metadata from the storage.
        """
        metadata_args = self.metadata_args
        self._last_metadata_args = metadata_args
        metadata = self.metadata_storage.get(self.name, *metadata_args)
        # apply dynamic metadata touchups
        if metadata.serapi_options is not None:
            metadata.serapi_options.iqr.pwd = self.path
        return metadata

    def _get_random_sentence_internal(
            self,
            filename: Optional[PathLike],
            glom_proofs: bool,
            **kwargs) -> List[CoqSentence]:
        if filename is None:
            obj = self.get_random_file(**kwargs)
        else:
            obj = self.get_file(filename, **kwargs)
        sentences = typing.cast(
            List[CoqSentence],
            self.extract_sentences(
                obj,
                'utf-8',
                glom_proofs,
                sentence_extraction_method=self.sentence_extraction_method,
                serapi_options=self.serapi_options,
                opam_switch=self.opam_switch,
                return_comments=False))
        return sentences

    def _iqr_bound_directories(
            self,
            relative: bool,
            return_I: bool = True,
            return_Q: bool = True,
            return_R: bool = True) -> Iterator[Path]:
        """
        Iterate over all physical paths in `serapi_options`.

        Parameters
        ----------
        relative : bool
            Flag to control whether iterator is over paths relative to
            project root or absolute paths
        return_I : bool, optional
            Flag controlling whether ``-I`` flag paths are returned, by
            default True
        return_Q : bool, optional
            Flag controlling whether ``-Q`` flag paths are returned, by
            default True
        return_R : bool, optional
            Flag controlling whether ``-R`` flag paths are returned, by
            default True

        Yields
        ------
        Path
            Physical paths from `serapi_options`.
        """
        if self.serapi_options is None:
            yield from []
        else:
            iqr = self.serapi_options.iqr
            for p in chain(iqr.I if return_I else (),
                           (p for p,
                            _ in iqr.Q) if return_Q else (),
                           (p for p,
                            _ in iqr.R) if return_R else ()):
                if relative:
                    yield Path(p)
                else:
                    yield self.path / p

    def _prepare_command(self, target: str) -> str:
        # wrap in parentheses to preserve operator precedence when
        # joining commands with &&
        commands = [f"({cmd})" for cmd in getattr(self, f"{target}_cmd")]
        if not commands:
            raise RuntimeError(
                f"{target.capitalize()} command not set for {self.name}.")
        return " && ".join(commands)

    def _process_command_output(
            self,
            action: str,
            returncode: int,
            stdout: str,
            stderr: str,
            ExcType: Type[ProjectBuildError] = ProjectBuildError) -> None:
        status = "failed" if returncode != 0 else "finished"
        msg = (
            f"{action} {status}! Return code is {returncode}! "
            f"stdout:\n{stdout}\n; stderr:\n{stderr}")
        if returncode != 0:
            raise ExcType(msg, returncode, stdout, stderr)
        else:
            # Use root logger instead of
            # self.logger for error message
            logger.debug(msg)
            self.logger.debug(f"Action ({action}) return code: {returncode}")

    def _make(
            self,
            target: str,
            action: str,
            max_memory: Optional[int] = None,
            max_runtime: Optional[int] = None) -> Tuple[int,
                                                        str,
                                                        str]:
        """
        Make a build target (one of build, clean, or install).

        Parameters
        ----------
        target : str
            One of ``"build"``, ``"clean"``, or ``"install"``.
        action : str
            A more descriptive term for the action represented by the
            build target, e.g., ``"compilation"``.
        max_memory: Optional[int], optional
            Max memory (bytes) allowed to make project.
        max_runtime: Optional[int], optional
            Max time (seconds) allowed to make project.

        Returns
        -------
        return_code : int
            The return code, expected to be 0.
        stdout : str
            The standard output of the command.
        stderr : str
            The standard error output of the command.

        Raises
        ------
        RuntimeError
            If no commands for this target are specified.
        ProjectBuildError
            If commands are specified but fail with nonzero exit code.
        TimeoutExpired
            If runtime of command exceeds `max_runtime`.
        """
        cmd = self._prepare_command(target)
        r = self.opam_switch.run(
            cmd,
            cwd=self.path,
            check=False,
            max_memory=max_memory,
            max_runtime=max_runtime)
        result = (r.returncode, r.stdout, r.stderr)
        self._process_command_output(action, *result)
        return result

    @abstractmethod
    def _pre_get_random(self, **kwargs):
        """
        Handle tasks needed before getting a random file (or pair, etc).
        """
        pass

    def _update_metadata(self, **kwargs) -> None:
        """
        Update fields of the current metadata.
        """
        self.metadata_storage.update(self.metadata, **kwargs)
        # update local copy separately to avoid redundant retrieval
        for name, value in kwargs.items():
            self.logger.debug(f"Updating {name}: {value}")
            setattr(self.metadata, name, value)

    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        with pushd(self.path):
            return [
                CoqDocument(
                    f,
                    project_path=self.path,
                    source_code=CoqParser.parse_source(f),
                    serapi_options=self.serapi_options)
                for f in self.get_file_list(relative=True)
            ]

    def _build(
            self,
            f: Callable[[],
                        _T],
            managed_switch_kwargs: Optional[Dict[str,
                                                 Any]] = None) -> _T:
        """
        Build the project.

        Parameters
        ----------
        f : Callable[[], _T]
            A function that will be executed to build the project with
            parametric artifacts.
        managed_switch_kwargs : Optional[Dict[str, Any]], optional
            A dictionary containing keyword arguments to
            `managed_switch`.

        Returns
        -------
        _T
            The output of the build process.

        Raises
        ------
        ProjectBuildError
            If the command(s) for building the project encounter an
            error.
        """
        # EVENT: <>.build
        self.logger.debug("Performing Project Build")
        if managed_switch_kwargs is None:
            managed_switch_kwargs = {}
        switch_manager = managed_switch_kwargs.get(
            'switch_manager',
            self.switch_manager)
        original_switch = self.opam_switch
        try:
            with self.managed_switch(**managed_switch_kwargs):
                result = f()
        except ProjectBuildError as e:
            m = self._missing_dependency_pattern.search(
                '\n'.join([e.stdout,
                           e.stderr]))
            if m is not None:
                # EVENT: <>.build
                self.logger.debug("Missing dependencies prevented build")
                self.infer_opam_dependencies()
                if switch_manager is not None:
                    # try to build again with fresh dependencies
                    release = managed_switch_kwargs.get('release', True)
                    if not release and original_switch != self.opam_switch:
                        # release flawed switch if it is not already
                        # released
                        switch_manager.release_switch(self.opam_switch)
                        self.opam_switch = original_switch
                    # force reattempt build
                    with self.project_logger(logger.getChild('force-rebuild')):
                        # EVENT: <>.build.force-rebuild
                        self.logger.debug("Forcing Rebuild")
                        with self.managed_switch(**managed_switch_kwargs):
                            result = f()
                else:
                    raise e
            else:
                raise e
        return result

    def build(
            self,
            managed_switch_kwargs: Optional[Dict[str,
                                                 Any]] = None,
            **kwargs) -> Tuple[int,
                               str,
                               str]:
        """
        Build the project.

        If serapi_options is not present or if it is incorrect before
        the build, build while inferring serapi_options; otherwise,
        build normally.

        If serapi_options is incorrect after building, infer
        serapi_options after building and concatenate the results of the
        builds.

        If the project's current switch has missing or incorrect
        dependencies as indicated by standard error output, then
        dependencies are freshly inferred.
        If a switch manager is available, then a new switch is obtained
        with the dependencies and the build is re-attempted.

        Parameters
        ----------
        managed_switch_kwargs : Optional[Dict[str, Any]], optional
            A dictionary containing keyword arguments to
            `managed_switch`.
        max_memory: Optional[int], optional
            Max memory (bytes) allowed to make project.
        max_runtime: Optional[int], optional
            Max time (seconds) allowed to make project.

        Returns
        -------
        return_code : int
            The exit code of the build process.
        stdout : str
            The captured standard output of the build process.
        stderr : str
            The captured standard error of the build process.

        Raises
        ------
        ProjectBuildError
            If the command(s) use to build the project encounter an
            error.

        See Also
        --------
        managed_switch : For valid `managed_switch_kwargs`
        """
        logger = self.logger.getChild('build')
        if not self._check_serapi_option_health_pre_build():
            # EVENT: <>.build
            logger.debug("Pre-Build Health Check Fail")
            with self.project_logger(logger.getChild('pre-build')):
                # logs will have name <>.build.pre-build
                (_,
                 rcode,
                 stdout,
                 stderr) = self.infer_serapi_options(
                     managed_switch_kwargs,
                     **kwargs)
            return rcode, stdout, stderr
        else:
            with self.project_logger(logger):
                # logs will have name <>.build
                (rcode,
                 stdout,
                 stderr) = self._build(
                     lambda: self._make("build",
                                        "Compilation",
                                        **kwargs),
                     managed_switch_kwargs)
        if not self._check_serapi_option_health_post_build():
            # EVENT: <>.build
            logger.debug("Post-Build Health Check Fail")
            separator = "\n@@\nInferring SerAPI Options...\n@@\n"
            with self.project_logger(logger.getChild('post-build')):
                # logs will have name <>.build.post-build
                (_,
                 rcode,
                 stdout_post,
                 stderr_post) = self.infer_serapi_options(
                     managed_switch_kwargs,
                     **kwargs)
            stdout = "".join((stdout, separator, stdout_post))
            stderr = "".join((stderr, separator, stderr_post))
        return rcode, stdout, stderr

    def clean(self, **kwargs) -> Tuple[int, str, str]:
        """
        Clean the build status of the project.
        """
        r = self._make("clean", "Cleaning", **kwargs)
        # ensure removal of Coq library files
        self._clean()
        return r

    def depends_on(
            self,
            package_name: str,
            package_version: Optional[Union[str,
                                            Version]]) -> bool:
        """
        Return whether this project depends on the given opam package.

        Parameters
        ----------
        package_name : str
            The name of an opam package.
        package_version : Optional[Union[str, Version]]
            A specific version of the package with which to narrow the
            check, by default None.

        Returns
        -------
        bool
            True if this project depends on the indicated package
            according to existing project metadata, False otherwise.
        """
        formula = self.get_dependency_formula()
        if package_version is None:
            is_dependency = package_name in formula.packages
        else:
            if isinstance(package_version, str):
                package_version = Version.parse(package_version)
            is_dependency = bool(
                formula.simplify({package_name: package_version}))
        return is_dependency

    def filter_files(
            self,
            files: Iterable[PathLike],
            relative: bool = False,
            dependency_order: bool = False) -> List[str]:
        """
        Filter and sort the given files relative to this project.

        Parameters
        ----------
        files : Iterable[PathLike]
            A collection of files, presumed to belong to this project.
        relative : bool, optional
            Whether to return absolute file paths or paths relative to
            the root of the project, by default False.
        dependency_order : bool, optional
            Whether to return the files in dependency order or not, by
            default False.
            Dependency order means that if one file ``foo`` depends
            upon another file ``bar``, then ``bar`` will appear
            before ``foo`` in the returned list.
            If False, then the files are sorted lexicographically.

        Returns
        -------
        List[str]
            The list of absolute (or `relative`) paths to all Coq files
            in the project sorted according to `dependency_order`, not
            including those ignored by `ignore_path_regex`.

        Raises
        ------
        MissingMetadataError
            If `dependency_order` is True but `serapi_options` is None.
        """
        root = self.path
        ignore_regex = self.ignore_path_regex
        filtered = []
        for file in files:
            file = get_relative_path(file, root)
            file_str = str(file)
            if ignore_regex.match(file_str) is None:
                # file should be kept
                filtered.append(str(root / file) if not relative else file_str)
        if dependency_order:
            if self.serapi_options is None:
                raise MissingMetadataError(
                    f"The `serapi_options` for {self.name} are not set; "
                    "cannot return files in dependency order. "
                    "Please try rebuilding the project.")
            filtered = order_dependencies(
                filtered,
                str(self.serapi_options.iqr),
                self.opam_switch,
                cwd=str(self.path))
        else:
            filtered = sorted(filtered)
        return filtered

    def get_dependency_formula(
            self,
            coq_version: Optional[Union[str,
                                        Version]] = None,
            ocaml_version: Optional[Union[str,
                                          Version]] = None) -> PackageFormula:
        """
        Get a formula for this project's dependencies.

        Parameters
        ----------
        coq_version : Optional[Union[str, Version]], optional
            If given, then include a dependency on Coq that matches the
            given major and minor components of `coq_version`.
        ocaml_version : Optional[Union[str, Version]], optional
            If given, then include a dependency on OCaml that matches
            the given major and minor components of `ocaml_version`.

        Returns
        -------
        PackageFormula
            A formula that can be used to retrieve an appropriate
            switch from a pool of existing switches or used to install
            required dependencies in a given switch.
        """
        formula = []
        # Loosen restriction to matching major.minor~prerelease
        if coq_version is not None:
            formula.append(major_minor_version_bound("coq", coq_version))
        formula.append(PackageFormula.parse('"coq-serapi"'))
        if ocaml_version is not None:
            formula.append(major_minor_version_bound("ocaml", ocaml_version))
        for dependency in self.opam_dependencies:
            formula.append(PackageFormula.parse(dependency))
        formula = reduce(
            lambda left,
            right: LogicalPF(left,
                             LogOp.AND,
                             right),
            formula[1 :],
            formula[0])
        return formula

    def get_file(self, filename: PathLike) -> CoqDocument:
        """
        Return a specific Coq source file.

        Parameters
        ----------
        filename : PathLike
            The path to a file within the project.

        Returns
        -------
        CoqDocument
            A CoqDocument corresponding to the selected Coq source file

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"
        """
        if not isinstance(filename, str):
            filename = str(filename)
        if not filename.endswith(".v"):
            raise ValueError("filename must end in .v")
        return CoqDocument(
            get_relative_path(filename,
                              self.path),
            project_path=self.path,
            source_code=CoqParser.parse_source(filename),
            serapi_options=self.serapi_options)

    def get_file_dependencies(self) -> Dict[str, List[str]]:
        """
        Get a map from filenames to their in-project dependencies.

        The map is equivalent to an adjacency list of the project's
        inter-file dependency graph, which contains directed edges from
        a file ``A`` to a file ``B`` if ``B`` depends upon ``A``.

        Returns
        -------
        Dict[str, List[str]]
            A map from filenames relative to the root of the project to
            sets of other relative filenames in the project upon which
            they depend.

        Raises
        ------
        MissingMetadataError
            If `serapi_options` are not set.
        """
        if self.coq_options is None:
            raise MissingMetadataError(
                "Cannot get file dependencies with unknown IQR flags")
        G = make_dependency_graph(
            typing.cast(List[PathLike],
                        self.get_file_list(relative=False)),
            self.coq_options,
            self.opam_switch,
            str(self.path))
        return {u: sorted(N.keys()) for u,
                N in G.adjacency()}

    def get_file_list(
            self,
            relative: bool = False,
            dependency_order: bool = False) -> List[str]:
        """
        Return a list of all Coq files associated with this project.

        See Also
        --------
        filter_files : For details on the parameters and return value.
        """
        return self.filter_files(
            pathlib.Path(self.path).rglob("*.v"),
            relative,
            dependency_order)

    def get_random_file(self, **kwargs) -> CoqDocument:
        """
        Return a random Coq source file.

        Returns
        -------
        CoqDocument
            A random Coq source file in the form of a CoqDocument
        """
        self._pre_get_random(**kwargs)
        files = self._traverse_file_tree()
        result = random.choice(files)
        return result

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            **kwargs) -> str:
        """
        Return a random sentence from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        str
            A random sentence from the project
        """
        sentences = self._get_random_sentence_internal(
            filename,
            glom_proofs,
            **kwargs)
        sentence = random.choice(sentences)
        return str(sentence)

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[PathLike] = None,
            glom_proofs: bool = True,
            **kwargs) -> Tuple[str,
                               str]:
        """
        Return a random adjacent sentence pair from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[PathLike], optional
            Absolute path to file to load sentences from, by default
            None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        tuple of str
            A pair of adjacent sentences from the project, with the
            first sentence chosen at random.
        """
        sentences: List[str] = []
        counter = 0
        THRESHOLD = 100
        while len(sentences) < 2:
            if counter > THRESHOLD:
                raise RuntimeError(
                    "Can't find file with more than 1 sentence after",
                    THRESHOLD,
                    "attempts. Try different inputs.")
            sentences = self._get_random_sentence_internal(
                filename,
                glom_proofs,
                **kwargs)
            counter += 1
        first_sentence_idx = random.randint(0, len(sentences) - 2)
        first, second = sentences[first_sentence_idx : first_sentence_idx + 2]
        return str(first), str(second)

    def get_sentences(
        self,
        filename: PathLike,
        sentence_extraction_method: Optional[SentenceExtractionMethod] = None,
        **kwargs
    ) -> Union[List[CoqSentence],
               Tuple[List[CoqSentence],
                     List[CoqComment]]]:
        r"""
        Get the sentences of a Coq file within the project.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off via ``glom_proofs = False``.

        Parameters
        ----------
        filename : PathLike
            The path to a file in the project.
        sentence_extraction_method : Optional[\
                                         SentenceExtractionMethod],\
                                     optional
            Method by which sentences should be extracted
        kwargs : Dict[str, Any]
            Optional keyword arguments to `Project.extract_sentences`.

        Returns
        -------
        List[CoqSentence]
            The list of sentences extracted from the indicated file.
        List[CoqComment], optional
            The list of comments extracted from the indicated file if
            `return_comments` is a keyword argument and True.

        See Also
        --------
        extract_sentences : For expected keyword arguments.
        """
        if sentence_extraction_method is None:
            sentence_extraction_method = self.sentence_extraction_method
        document = self.get_file(filename)
        kwargs['sentence_extraction_method'] = sentence_extraction_method
        kwargs['opam_switch'] = self.opam_switch
        kwargs['serapi_options'] = self.serapi_options
        return self.extract_sentences(document, **kwargs)

    def infer_metadata(
            self,
            fields_to_infer: Optional[Iterable[str]] = None) -> Dict[str,
                                                                     Any]:
        """
        Try to infer any missing metadata.

        Parameters
        ----------
        infer_fields : Optional[Iterable[str]], optional
            Optional fields for which inference of new values should be
            performed even if already defined, by default None.
            The names should match attributes of `ProjectMetadata`.

        Returns
        -------
        Dict[str, Any]
            The values for each newly inferred field.
        """
        if fields_to_infer is None:
            fields_to_infer = set()
        else:
            fields_to_infer = set(fields_to_infer)
        current_metadata = self.metadata
        for f in fields(ProjectMetadata):
            if (getattr(current_metadata,
                        f.name) is None
                    and f.name not in ProjectMetadata.immutable_fields):
                fields_to_infer.add(f.name)
        # if the order of field inference matters, manually pop such
        # fields and infer them first before looping over the rest
        inferred_fields = {}
        for f in fields_to_infer:
            # force an attribute error for non-existent fields
            getattr(current_metadata, f)
            try:
                inferred_fields[f] = getattr(self, f'infer_{f}')()
            except AttributeError:
                raise NotImplementedError(
                    f"Cannot infer metadata field named '{f}'")
        return inferred_fields

    def infer_opam_dependencies(
            self,
            ignore_iqr_flags: bool = False,
            ignore_coq_version: bool = False) -> List[str]:
        """
        Try to infer Opam-installable dependencies for the project.

        Parameters
        ----------
        ignore_iqr_flags : bool, optional
            If True, then do not account for the project's own libraries
            when inferring dependencies.
            By default False.
        ignore_coq_version : bool, optional
            If True, then do not account for the current Coq version or
            standard libraries when inferring dependencies.
            By default False.

        Returns
        -------
        List[str]
            A conjunctive list of package formulas specifying
            dependencies that must be installed before the project is
            built.

        See Also
        --------
        PackageFormula : For more information about package formulas.
        """
        logger = self.logger.getChild('infer_opam_dependencies')
        try:
            formula = self.opam_switch.get_dependencies(self.path)
        except CalledProcessError:
            formula = None
        # possibly prone to false positives/negatives
        required_libraries = opamdep.get_required_libraries(
            self.path,
            self.path)
        dependencies = opamdep.guess_opam_packages(
            typing.cast(
                Dict[PathLike,
                     Set[opamdep.RequiredLibrary]],
                required_libraries),
            self.iqr_flags if not ignore_iqr_flags else None,
            self.coq_version if not ignore_coq_version else None)
        if formula is not None:
            # limit guessed dependencies to only novel ones
            changed = formula.packages.difference(dependencies)
            logger.debug(f"Inferred new dependencies: {changed}")
            dependencies.difference_update(formula.packages)
        # format dependencies as package constraints
        dependencies = [f'"{dep}"' for dep in dependencies]

        if isinstance(formula, PackageFormula):
            if isinstance(formula, LogicalPF):
                formula = formula.to_conjunctive_list()
            else:
                formula = [formula]
        if formula is not None:
            # extend opam file formula with guessed dependencies
            formula = [str(c) for c in formula]
            formula.extend(dependencies)
        else:
            formula = dependencies
        with self.project_logger(logger):
            # logs will have <>.infer_serapi_options
            self._update_metadata(opam_dependencies=formula)
        return formula

    def infer_serapi_options(
            self,
            managed_switch_kwargs: Optional[Dict[str,
                                                 Any]] = None,
            **kwargs) -> Tuple[SerAPIOptions,
                               int,
                               str,
                               str]:
        """
        Build project and get SerAPI options, simultaneously.

        Invoking this function will replace any serapi_options already
        present in the metadata.

        Parameters
        ----------
        kwargs
            Keyword arguments to `OpamSwitch.run`.

        Returns
        -------
        SerAPIOptions
            The inferred SerAPI options.
        int
            The return code of the last-executed command
        str
            The total stdout of all commands run
        str
            The total stderr of all commands run
        """
        # ensure we are building from a clean slate
        logger = self.logger.getChild('infer_serapi_options')
        logger.debug('Inferring serapi options')
        try:
            self.clean(**kwargs)
        except ProjectBuildError:
            # cleaning may fail if nothing to clean or the project has
            # not yet been configured by a prior build
            logger.debug("cleaning failed")
            pass

        def _strace_build():
            cmd = self._prepare_command("build")
            contexts, rcode_out, stdout, stderr = strace_build(
                self.opam_switch,
                cmd,
                workdir=self.path,
                check=False,
                **kwargs)
            self._process_command_output("Strace", rcode_out, stdout, stderr)
            return contexts, rcode_out, stdout, stderr

        # Event
        logger.debug('Performing strace build')
        with self.project_logger(logger.getChild('strace')):
            # logs will have <>.infer_serapi_options.strace
            (contexts,
             rcode_out,
             stdout,
             stderr) = self._build(_strace_build,
                                   managed_switch_kwargs)

        serapi_options = SerAPIOptions.merge(
            [c.serapi_options for c in contexts],
            root=self.path)
        logger.debug(f'Found serapi options: {serapi_options}')
        with self.project_logger(logger):
            # logs will have <>.infer_serapi_options
            self._update_metadata(serapi_options=serapi_options)
        return serapi_options, rcode_out, stdout, stderr

    install = partialmethod(_make, "install", "Installation")
    """
    Install the project system-wide in "coq-contrib".
    """

    def run(self,
            cmd: str,
            action: Optional[str] = None,
            **kwargs) -> Tuple[int,
                               str,
                               str]:
        """
        Run a command in the context of the project.

        Parameters
        ----------
        cmd : str
            An arbitrary command.
        action : Optional[str], optional
            A short description of the command, by default None.
        kwargs : Dict[str, Any]
            Optional keywords arguments to `OpamSwitch.run`.

        Returns
        -------
        return_code : int
            The return code, expected to be 0.
        stdout : str
            The standard output of the command.
        stderr : str
            The standard error output of the command.

        Raises
        ------
        ProjectCommandError
            If the command fails with nonzero exit code.
        """
        r = self.opam_switch.run(cmd, check=False, **kwargs)
        result = (r.returncode, r.stdout, r.stderr)
        if action is None:
            action = escape(cmd)
        self._process_command_output(
            action,
            *result,
            ExcType=ProjectCommandError)
        return result

    @contextmanager
    def managed_switch(
        self,
        coq_version: Optional[Union[str,
                                    Version]] = None,
        variables: Optional[AssignedVariables] = None,
        release: bool = True,
        switch_manager: Optional[SwitchManager] = None,
    ) -> Generator[OpamSwitch,
                   None,
                   None]:
        """
        Yield a context with a switch matching given constraints.

        For the duration of the context, this project's switch will be
        set to a managed switch obtained from the project's switch
        manager.

        Parameters
        ----------
        coq_version : Optional[Union[str, Version]], optional
            A version of Coq that the managed switch should have
            installed, by default None.
        variables : Optional[AssignedVariables], optional
            Optional variables that may impact interpretation of the
            project's dependency formula and override those of the
            switch manager, by default None.
        release : bool, optional
            Whether to release the managed switch upon exiting the
            context.
            A switch that has been released cannot safely be used again.
        switch_manager : Optional[SwitchManager], optional
            An optional switch manager that will override the project's
            manager.

        Yields
        ------
        OpamSwitch
            The original switch so that it can be restored manually if
            `release` is False.

        Raises
        ------
        RuntimeError
            If `coq_version` or `variables` is not None and both
            `switch_manager` and ``self.switch_manager`` are None.
        """
        dependency_formula = self.get_dependency_formula(coq_version)
        managed_switch_requested = (
            coq_version is not None and variables is not None)
        if variables is None:
            variables = {}
        if switch_manager is None:
            switch_manager = self.switch_manager
        is_switch_stale = False
        if switch_manager is not None:
            is_switch_stale = switch_manager.satisfies(
                self.opam_switch,
                dependency_formula,
                **variables)
        managed_switch_requested = managed_switch_requested or is_switch_stale
        if managed_switch_requested and switch_manager is None:
            raise RuntimeError(
                "Cannot use managed switch without a switch manager")
        original_switch = self.opam_switch
        logger = self.logger.getChild('managed_switch')
        try:
            if managed_switch_requested and switch_manager is not None:
                self.opam_switch = switch_manager.get_switch(
                    dependency_formula,
                    variables)
            logger.debug("Using Managed Switch Context")
            yield original_switch
        finally:
            if managed_switch_requested and switch_manager is not None and release:
                switch_manager.release_switch(self.opam_switch)
                self.opam_switch = original_switch
            logger.debug("Exiting Managed Switch Context")

    @contextmanager
    def project_logger(
        self,
        logger: logging.Logger,
    ) -> Generator[logging.Logger,
                   None,
                   None]:
        """
        Yield context is specific logger for project.

        Parameters
        ----------
        logger : logging.Logger
            Logger to use to send logging messages.

        Yields
        ------
        logging.Logger
            The original logger used before this context.
        """
        original_logger = self.logger
        try:
            self.logger = logger
            yield original_logger
        finally:
            self.logger = original_logger

    @staticmethod
    def extract_sentences(
        document: CoqDocument,
        encoding: str = 'utf-8',
        glom_proofs: bool = True,
        glom_ltac: bool = False,
        return_asts: bool = False,
        sentence_extraction_method: SEM = SEM.SERAPI,
        **kwargs
    ) -> Union[List[CoqSentence],
               Tuple[List[CoqSentence],
                     List[CoqComment]]]:
        """
        Split the Coq file text by sentences.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off.

        .. warning::
            If the sentence extraction method relies upon an OCaml
            package such as `coq-serapi`, then an
            ``opam_switch : OpamSwitch`` keyword argument should be
            provided to set the environment of execution

        Parameters
        ----------
        document : CoqDocument
            A Coq document.
        encoding : str, optional
            The encoding to use for decoding if a bytestring is
            provided, by default 'utf-8'
        glom_proofs : bool, optional
            A flag indicating whether or not proofs should be re-glommed
            after sentences are split, by default `True`
        glom_ltacs: bool, optional
            Glom together contiguous regions of Ltac code,
            by default `False`
        return_asts: bool, optional
            Return asts with sentences as a list of tuples,
            by default `False`
        sentence_extraction_method : SentenceExtractionMethod
            Method by which sentences should be extracted
        kwargs
            Keyword arguments for heuristic parsing.

        Returns
        -------
        List[CoqSentence]
            A list of Coq sentences extracted from the given `document`.
        List[CoqComment], optional
            The list of comments extracted from the indicated file if
            `return_comments` is a keyword argument and True.

        See Also
        --------
        HeuristicParser.parse_sentences_from_document : For keyword args
        """
        return sentence_extraction_method.parser(
        ).parse_sentences_from_document(
            document,
            encoding,
            glom_proofs,
            glom_ltac=glom_ltac,
            return_asts=return_asts,
            **kwargs)

    @staticmethod
    def get_local_modpath(filename: PathLike, iqr: IQR) -> str:
        """
        Infer the module path for the given file.

        Parameters
        ----------
        filename : PathLike
            The physical path to a project file relative to the project
            root.
        iqr : IQR
            Arguments with which to initialize `sertop`, namely IQR
            flags.

        Returns
        -------
        modpath : str
            The logical library path one would use if the indicated file
            was imported or required in another.
        """
        # strip file extension, if any
        if not isinstance(filename, pathlib.Path):
            filename = pathlib.Path(filename)
        filename = str(filename.with_suffix(''))
        # identify the correct logical library prefix for this filename
        matched = False
        dot_log = None
        for (phys, log) in (iqr.Q | iqr.R):
            if filename.startswith(phys):
                filename = filename[len(phys):]
            else:
                if phys == ".":
                    dot_log = log
                continue
            # ensure that the filename gets separated from the logical
            # prefix by a path separator (to be replaced with a period)
            if filename[0] != os.path.sep:
                sep = os.path.sep
            else:
                sep = ''
            filename = sep.join([log, filename])
            matched = True
            break
        if not matched and dot_log is not None:
            # ensure that the filename gets separated from the logical
            # prefix by a path separator (to be replaced with a period)
            if filename[0] != os.path.sep:
                sep = os.path.sep
            else:
                sep = ''
            filename = sep.join([dot_log, filename])
        # else we implicitly map the working directory to an empty
        # logical prefix
        # convert rest of physical path to logical
        path = filename.split(os.path.sep)
        if path == ['']:
            path = []
        modpath = ".".join([dirname.capitalize() for dirname in path])
        return modpath
