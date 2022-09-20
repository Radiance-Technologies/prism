"""
Module providing Coq project class representations.
"""

import logging
import os
import pathlib
import random
import re
from abc import ABC, abstractmethod
from dataclasses import fields
from enum import Enum, auto
from functools import partialmethod, reduce
from subprocess import CalledProcessError
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple, Union

from prism.data.document import CoqDocument
from prism.language.gallina.analyze import SexpInfo
from prism.language.gallina.parser import CoqParser
from prism.language.heuristic.parser import HeuristicParser, SerAPIParser
from prism.project.exception import ProjectBuildError
from prism.project.iqr import IQR
from prism.project.metadata import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.strace import strace_build
from prism.util.build_tools.coqdep import order_dependencies
from prism.util.logging import default_log_level
from prism.util.opam import OpamSwitch, PackageFormula
from prism.util.opam.formula.package import LogicalPF
from prism.util.path import get_relative_path
from prism.util.radpytools.os import pushd
from prism.util.re import regex_from_options

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(default_log_level())


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

    def parser(self) -> Union[HeuristicParser, SerAPIParser]:
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

    Attributes
    ----------
    dir_abspath : str
        The absolute path to the project's root directory.
    metadata: ProjectMetadata
        Project metadata containing information such as project name
        and commands.
    size_bytes : int
        The total space on disk occupied by the files in the dir in
        bytes
    sentence_extraction_method : SentenceExtractionMethod
        The method by which sentences are extracted.
    """

    coq_library_exts = ["*.vio", "*.vo", "*.vos", "*.vok"]
    """
    A list of possible Coq library file extensions.
    """

    def __init__(
            self,
            dir_abspath: os.PathLike,
            metadata_storage: MetadataStorage,
            opam_switch: Optional[OpamSwitch] = None,
            sentence_extraction_method: SEM = SentenceExtractionMethod.SERAPI,
            num_cores: Optional[int] = None):
        """
        Initialize Project object.
        """
        self.dir_abspath = dir_abspath
        self.metadata_storage = metadata_storage
        self.size_bytes = self._get_size_bytes()
        self.sentence_extraction_method = sentence_extraction_method
        if opam_switch is not None:
            self.opam_switch = opam_switch
        else:
            self.opam_switch = OpamSwitch()
        self.num_cores = num_cores
        self._last_metadata_args: MetadataArgs = None
        self._metadata: ProjectMetadata = None

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
    def coq_version(self) -> str:
        """
        Get the version of OCaml installed in the project's switch.
        """
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
    def ocaml_version(self) -> str:
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

    @property
    @abstractmethod
    def path(self) -> os.PathLike:
        """
        Get the path to the project's root directory.
        """
        pass

    @property
    def serapi_options(self) -> Optional[str]:
        """
        Get the SerAPI options for parsing this project's files.

        If None, then the SerAPI options have not yet been determined
        and will be inferred automatically the next time the project is
        built.

        Returns
        -------
        Optional[str]
            The command-line options for invoking SerAPI tools, e.g.,
            ``f"sercomp {serapi_options} file.v"``.
        """
        return self.metadata.serapi_options

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
        return self.metadata_storage.get(self.name, *metadata_args)

    def _get_random_sentence_internal(
            self,
            filename: Optional[str],
            glom_proofs: bool,
            **kwargs):
        if filename is None:
            obj = self.get_random_file(**kwargs)
        else:
            obj = self.get_file(filename, **kwargs)
        sentences = self.extract_sentences(
            obj,
            'utf-8',
            glom_proofs,
            sentence_extraction_method=self.sentence_extraction_method,
            serapi_options=self.serapi_options,
            opam_switch=self.opam_switch)
        return sentences

    def _get_size_bytes(self) -> int:
        """
        Get size in bytes of working directory.

        This size should exclude the contents of any .git directories.
        """
        return sum(
            f.stat().st_size
            for f in pathlib.Path(self.path).glob('**/*')
            if f.is_file()) - sum(
                f.stat().st_size
                for f in pathlib.Path(self.path).glob('**/.git/**/*')
                if f.is_file())

    def _prepare_command(self, target: str) -> str:
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
            stderr: str) -> None:
        status = "failed" if returncode != 0 else "finished"
        msg = (
            f"{action} {status}! Return code is {returncode}! "
            f"stdout:\n{stdout}\n; stderr:\n{stderr}")
        if returncode != 0:
            raise ProjectBuildError(msg, returncode, stdout, stderr)
        else:
            logger.debug(msg)

    def _make(self, target: str, action: str) -> Tuple[int, str, str]:
        """
        Make a build target (one of build, clean, or install).

        Parameters
        ----------
        target : str
            One of ``"build"``, ``"clean"``, or ``"install"``.
        action : str
            A more descriptive term for the action represented by the
            build target, e.g., ``"compilation"``.

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
        """
        # wrap in parentheses to preserve operator precedence when
        # joining commands with &&
        cmd = self._prepare_command(target)
        r = self.opam_switch.run(cmd, cwd=self.path, check=False)
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
                    source_code=CoqParser.parse_source(f))
                for f in self.get_file_list(relative=True)
            ]

    def build(self) -> Tuple[int, str, str]:
        """
        Build the project.
        """
        if self.serapi_options is None:
            _, rcode, stdout, stderr = self.infer_serapi_options()
            return rcode, stdout, stderr
        else:
            return self._make("build", "Compilation")

    def clean(self) -> Tuple[int, str, str]:
        """
        Clean the build status of the project.
        """
        r = self._make("clean", "Cleaning")
        # ensure removal of Coq library files
        self._clean()
        return r

    def filter_files(
            self,
            files: Iterable[os.PathLike],
            relative: bool = False,
            dependency_order: bool = False) -> List[str]:
        """
        Filter and sort the given files relative to this project.

        Parameters
        ----------
        files : Iterable[os.PathLike]
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
        RuntimeError
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
            iqr = self.serapi_options
            if iqr is None:
                raise RuntimeError(
                    f"The `serapi_options` for {self.name} are not set; "
                    "cannot return files in dependency order. "
                    "Please try rebuilding the project.")
            filtered = order_dependencies(
                filtered,
                self.opam_switch,
                iqr.replace(",",
                            " "))
        else:
            filtered = sorted(filtered)
        return filtered

    def get_file(self, filename: os.PathLike) -> CoqDocument:
        """
        Return a specific Coq source file.

        Parameters
        ----------
        filename : os.PathLike
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
            source_code=CoqParser.parse_source(filename))

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
        return sentence

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            glom_proofs: bool = True,
            **kwargs) -> List[str]:
        """
        Return a random adjacent sentence pair from the project.

        Filename is random unless it is provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True

        Returns
        -------
        List of str
            A list of two adjacent sentences from the project, with the
            first sentence chosen at random
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
        return sentences[first_sentence_idx : first_sentence_idx + 2]

    def get_sentences(
            self,
            filename: os.PathLike,
            sentence_extraction_method: Optional[
                SentenceExtractionMethod] = None,
            **kwargs) -> Union[List[str],
                               Tuple[List[str],
                                     List[SexpInfo.Loc]]]:
        r"""
        Get the sentences of a Coq file within the project.

        By default, proofs are then re-glommed into their own entries.
        This behavior can be switched off via ``glom_proofs = False``.

        Parameters
        ----------
        filename : os.PathLike
            The path to a file in the project.
        sentence_extraction_method : Optional[\
                                         SentenceExtractionMethod],\
                                     optional
            Method by which sentences should be extracted
        kwargs : Dict[str, Any]
            Optional keyword arguments to `Project.extract_sentences`.

        Returns
        -------
        List[str]
            A list of strings corresponding to Coq source file
            sentences, with proofs glommed (or not) depending on input
            flag.
        List[SexpInfo.Loc], optional
            A list of locations corresponding to the returned list of
            sentences. This list is only returned if certain arguments
            are passed to certain parsers. With the default args, this
            is NOT returned.

        See Also
        --------
        extract_sentences : For expected keyword arguments.
        """
        if sentence_extraction_method is None:
            sentence_extraction_method = self.sentence_extraction_method
        document = self.get_file(filename)
        kwargs['sentence_extraction_method'] = sentence_extraction_method
        kwargs['opam_switch'] = self.opam_switch
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

    def infer_opam_dependencies(self) -> List[str]:
        """
        Try to infer Opam-installable dependencies for the project.

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
        try:
            formula = self.opam_switch.get_dependencies(self.path)
        except CalledProcessError:
            # TODO: try to infer dependencies by other means
            formula = []
            return formula
        if isinstance(formula, PackageFormula):
            if isinstance(formula, LogicalPF):
                formula = formula.to_conjunctive_list()
            else:
                formula = [formula]
        formula = [str(c) for c in formula]
        self._update_metadata(opam_dependencies=formula)
        return formula

    def infer_serapi_options(self) -> Tuple[str, int, str, str]:
        """
        Build project and get IQR options, simultaneously.

        Invoking this function will replace any serapi_options already
        present in the metadata.

        Returns
        -------
        str
            The IQR flags string that should be stored in serapi_options
        int
            The return code of the last-executed command
        str
            The total stdout of all commands run
        str
            The total stderr of all commands run
        """
        # ensure we are building from a clean slate
        try:
            self.clean()
        except ProjectBuildError:
            # cleaning may fail if nothing to clean or the project has
            # not yet been configured by a prior build
            pass
        cmd = self._prepare_command("build")
        contexts, rcode_out, stdout, stderr = strace_build(
            self.opam_switch,
            cmd,
            workdir=self.path,
            check=False)
        self._process_command_output("Strace", rcode_out, stdout, stderr)

        def or_(x, y):
            return x | y

        serapi_options = str(
            reduce(
                or_,
                [c.iqr for c in contexts],
                IQR(set(),
                    set(),
                    set(),
                    self.path)))
        self._update_metadata(serapi_options=serapi_options)
        return serapi_options, rcode_out, stdout, stderr

    install = partialmethod(_make, "install", "Installation")
    """
    Install the project system-wide in "coq-contrib".
    """

    @staticmethod
    def extract_sentences(
            document: CoqDocument,
            encoding: str = 'utf-8',
            glom_proofs: bool = True,
            glom_ltac: bool = False,
            return_asts: bool = False,
            sentence_extraction_method: SEM = SEM.SERAPI,
            **kwargs) -> Union[List[str],
                               Tuple[List[str],
                                     List[SexpInfo.Loc]]]:
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

        Returns
        -------
        List[str]
            A list of strings corresponding to Coq source file
            sentences, with proofs glommed (or not) depending on input
            flag.
        List[SexpInfo.Loc], optional
            A list of locations corresponding to the returned list of
            sentences. This list is only returned if certain arguments
            are passed to certain parsers. With the default args, this
            is NOT returned.
        """
        return sentence_extraction_method.parser(
        ).parse_sentences_from_document(
            document,
            encoding,
            glom_proofs,
            glom_ltac=glom_ltac,
            return_asts=return_asts,
            **kwargs)
