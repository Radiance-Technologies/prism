"""
Defines central storage/retrieval mechanisms for project metadata.
"""

import re
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Set, TypeVar

import seutil.bash as bash

from prism.project.metadata.dataclass import ProjectMetadata
from prism.util.opam import OpamAPI, Version

T = TypeVar('T')
Table = Dict[T, T]


@dataclass(frozen=True)
class ProjectSource:
    """
    Identifies a source repository for a project.
    """

    project_name: str
    repo_url: Optional[str]


@dataclass(frozen=True)
class Revision:
    """
    Identifies a commit in a repository.
    """

    project_source: ProjectSource
    commit_sha: Optional[str]

    def __post_init__(self):
        """
        Ensure that a commit requires a repository.
        """
        if self.project_source.repo_url is None and self.commit_sha is not None:
            raise ValueError(
                "A commit cannot be given if the project URL is not given.")


@dataclass(frozen=True)
class Context:
    """
    Identifies a build environment.
    """

    revision: Revision
    coq_version: Optional[Version]
    ocaml_version: Optional[Version]

    def __post_init__(self):
        """
        Ensure that an OCaml version requires a Coq version.
        """
        if self.ocaml_version is not None and self.coq_version is None:
            raise ValueError(
                "A Coq version must be specified if an OCaml version is given.")


@dataclass(frozen=True)
class CommandSequence:
    """
    A sequence of commands.
    """

    commands: List[str]


@dataclass
class SerAPIOptions:
    """
    Specifies SerAPI options for a build environment.
    """

    context: Context
    serapi_options: str

    def __eq__(self, other: 'SerAPIOptions') -> bool:
        """
        Test for equivalence of SerAPI options.

        Only one option can be applied per context.
        """
        if not isinstance(other, SerAPIOptions):
            return NotImplemented
        else:
            return self.context == other.context

    def __hash__(self) -> int:
        """
        Get the hash of the SerAPI options.

        Only one option can be applied per context.
        """
        return hash(self.context)


@dataclass(frozen=True)
class OpamDependency:
    """
    Specifies an opam repository for a build environment.
    """

    context: Context
    opam_repo: str


@dataclass(frozen=True)
class OCamlDependency:
    """
    Specifies an OCaml package dependency for a build environment.
    """

    context: Context
    opam_package: str


@dataclass
class ProjectScript:
    """
    Specifies a script in an environment.
    """

    context: Context
    script: CommandSequence

    def __eq__(self, other: 'ProjectScript') -> bool:
        """
        Test for equivalence of two project-bound scripts.

        Only one script (of a type) can be applied per context.
        """
        if not isinstance(other, ProjectScript):
            return NotImplemented
        else:
            return self.context == other.context

    def __hash__(self) -> int:
        """
        Get the hash of the script.

        Only one script (of a type) can be applied per context.
        """
        return hash(self.context)


@dataclass(frozen=True)
class CoqOCamlCompability:
    """
    Records a pair of compatible Coq and OCaml compilers.
    """

    coq_version: Version
    ocaml_version: Version


@dataclass(frozen=True)
class SerAPICoqCompatibility:
    """
    Records a pair of compatible SerAPI/Coq versions.
    """

    coq_version: Version
    serapi_version: Version


@dataclass(frozen=True)
class MetadataStorage:
    """
    A central repository for project metadata.

    This class provides storage and retrieval methods for metadata
    across multiple projects and versions.
    """

    projects: Set[str]
    project_sources: Set[ProjectSource]
    revisions: Set[Revision]
    contexts: Set[Context]
    serapi_options: Table[SerAPIOptions]
    build_commands: Table[ProjectScript]
    install_commands: Table[ProjectScript]
    clean_commands: Table[ProjectScript]
    opam_repo_dependencies: Table[OpamDependency]
    coq_dependencies: Table[OCamlDependency]
    opam_dependencies: Table[OCamlDependency]
    # meta-metadata
    ocaml_packages: Set[str]
    opam_repositories: Set[str]
    coq_ocaml_compatibility: Set[CoqOCamlCompability]
    serapi_coq_compatibility: Set[SerAPICoqCompatibility]
    serapi_versions: Set[Version]
    coq_versions: Set[Version]
    ocaml_versions: Set[Version]
    command_sequences: Set[CommandSequence]

    def __post_init__(self) -> None:
        """
        Bootstrap version tables.
        """
        r = bash.run("opam show -f all-versions coq-serapi")
        r.check_returncode()
        serapi_versions = re.split(r"\s+", r.stdout)
        serapi_versions.pop()
        self.serapi_versions.update(Version.parse(sv) for sv in serapi_versions)

        r = bash.run("opam show -f all-versions coq")
        r.check_returncode()
        coq_versions = re.split(r"\s+", r.stdout)
        coq_versions.pop()
        self.coq_versions.update(Version.parse(cv) for cv in coq_versions)

        r = bash.run("opam show -f all-versions ocaml")
        r.check_returncode()
        ocaml_versions = re.split(r"\s+", r.stdout)
        ocaml_versions.pop()
        self.ocaml_versions.update(Version.parse(ov) for ov in ocaml_versions)

        serapi_coq_compat = []
        for serapi_version in serapi_versions:
            dependencies = OpamAPI.get_dependencies(
                "coq-serapi",
                str(serapi_version))
            coq_constraint = dependencies['coq']
            for coq_version in coq_versions:
                if coq_version in coq_constraint:
                    serapi_coq_compat.append(
                        SerAPICoqCompatibility(coq_version,
                                               serapi_version))
        self.serapi_coq_compatibility.update(serapi_coq_compat)

        coq_ocaml_compat = []
        for coq_version in coq_versions:
            dependencies = OpamAPI.get_dependencies("coq", str(coq_version))
            ocaml_constraint = dependencies['ocaml']
            for ocaml_version in ocaml_versions:
                if ocaml_version in ocaml_constraint:
                    coq_ocaml_compat.append(
                        CoqOCamlCompability(coq_version,
                                            ocaml_version))
        self.coq_ocaml_compatibility.update(coq_ocaml_compat)

    def _get_defaults(self, metadata: ProjectMetadata) -> List[ProjectMetadata]:
        """
        Get default metadata in increasing order of precedence.

        Parameters
        ----------
        metadata : ProjectMetadata
            A metadata record.

        Returns
        -------
        List[ProjectMetadata]
            A list of default metadata with lower precedence than the
            given record.
        """
        defaults = []
        for i in range(metadata.level - 1):
            try:
                view_i = metadata.at_level(i)
            except ValueError:
                continue
            else:
                try:
                    default = self.get(
                        view_i.project_name,
                        view_i.project_url,
                        view_i.commit_sha,
                        view_i.coq_version,
                        view_i.ocaml_version)
                except KeyError:
                    continue
                else:
                    defaults.append(default)
        return defaults

    def get(
            self,
            project_name: str,
            project_url: Optional[str] = None,
            commit_sha: Optional[str] = None,
            coq_version: Optional[str] = None,
            ocaml_version: Optional[str] = None) -> ProjectMetadata:
        """
        Get the metadata for the requested project and options.

        Parameters
        ----------
        project_name : str
            The name of a project.
        project_url : Optional[str], optional
            The URL of the project's (Git) repository, by default None.
        commit_sha : Optional[str], optional
            The commit SHA of a revision of the project, by default
            None.
        coq_version : Optional[str], optional
            The version of Coq against which the project should be
            built, by default None.
        ocaml_version : Optional[str], optional
            The version of the OCaml compiler against which the project
            should be built, by default None.

        Returns
        -------
        ProjectMetadata
            The requested metadata.

        Raises
        ------
        KeyError
            If the requested metadata does not exist.
        """
        ...

    def insert(self, metadata: ProjectMetadata) -> None:
        """
        Insert new metadata into the repository.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for some project.
        """
        project_source = ProjectSource(
            metadata.project_name,
            metadata.project_url)
        revision = Revision(project_source, metadata.commit_sha)
        context = Context(
            revision,
            metadata.coq_version,
            metadata.ocaml_version)
        self.projects.add(metadata.project_name)
        self.project_sources.add(project_source)
        self.revisions.add(revision)
        self.contexts.add(context)
        # only store new data if it overrides all values with lower
        # precedence
        ...

    def __iter__(self) -> Iterator[ProjectMetadata]:
        """
        Iterate over the stored metadata.

        The order of iteration is not guaranteed.
        """
        yield from (
            self.get(
                context.revision.project_source.project_name,
                context.revision.project_source.repo_url,
                context.revision.commit_sha,
                context.coq_version,
                context.ocaml_version) for context in self.contexts)
