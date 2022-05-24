"""
Defines central storage/retrieval mechanisms for project metadata.
"""

import os
from dataclasses import dataclass, fields
from typing import (
    Any,
    ClassVar,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)

import seutil.io as io
from bidict import bidict
from radpytools.dataclasses import default_field

from prism.project.metadata.dataclass import ProjectMetadata
from prism.util.opam import OCamlVersion, Version

from .version_info import version_info

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
        if isinstance(self.coq_version, str):
            object.__setattr__(
                self,
                'coq_version',
                OCamlVersion.parse(self.coq_version))
        if isinstance(self.ocaml_version, str):
            object.__setattr__(
                self,
                'ocaml_version',
                OCamlVersion.parse(self.ocaml_version))
        if not version_info.are_coq_ocaml_compatible(self.coq_version,
                                                     self.ocaml_version):
            raise RuntimeError(
                f"Incompatible Coq/OCaml versions specified: coq={self.coq_version}, "
                f"ocaml={self.ocaml_version}")


@dataclass(frozen=True)
class CommandSequence:
    """
    A sequence of commands.
    """

    commands: List[str]

    def __hash__(self) -> int:  # noqa: D105
        return hash(tuple(self.commands))


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
class IgnorePathRegex:
    """
    Specifies path(s) in a project that should be ignored.
    """

    context: Context
    regex: str


@dataclass
class MetadataStorage:
    """
    A central repository for project metadata.

    This class provides storage and retrieval methods for metadata
    across multiple projects and versions.
    """

    # options
    autofill: bool = True
    """
    Whether to automatically fill in undefined, required metadata fields
    with default values during retrieval.
    """
    # final fields that establish identity of metadata records
    projects: Set[str] = default_field(set())
    project_sources: Set[ProjectSource] = default_field(set())
    revisions: Set[Revision] = default_field(set())
    contexts: Dict[Context, int] = default_field(dict())
    # one-to-one overridable fields
    # match metadata field names exactly
    serapi_options: Dict[int, str] = default_field(dict())
    build_cmd: Dict[int, int] = default_field(dict())
    install_cmd: Dict[int, int] = default_field(dict())
    clean_cmd: Dict[int, int] = default_field(dict())
    # one-to-many overridable fields
    # match metadata field names exactly
    opam_repos: Dict[int, Set[str]] = default_field(dict())
    coq_dependencies: Dict[int, Set[str]] = default_field(dict())
    opam_dependencies: Dict[int, Set[str]] = default_field(dict())
    ignore_path_regex: Dict[int, Set[str]] = default_field(dict())
    # meta-metadata
    ocaml_packages: Set[str] = default_field(set())
    opam_repositories: Set[str] = default_field(set())
    command_sequences: bidict[CommandSequence, int] = default_field(bidict())
    # incrementable IDs
    next_context_id: int = 0
    next_command_sequence_id: int = 0
    # default fields
    default_coq_version: str = '8.10.2'
    default_serapi_version: str = '8.10.0+0.7.2'
    default_ocaml_version: str = '4.07.2'
    default_serapi_options: str = ""
    default_build_cmd: List[str] = default_field([])
    default_install_cmd: List[str] = default_field([])
    default_clean_cmd: List[str] = default_field([])
    # class variables
    _final_fields: ClassVar[Set[str]] = {
        'project_name',
        'project_url',
        'coq_version',
        'ocaml_version',
        'commit_sha',
        'serapi_version'
    }
    """
    Metadata fields that cannot be overridden.
    """

    def __post_init__(self) -> None:
        """
        Bootstrap version tables and IDs.
        """
        if self.contexts:
            self.next_context_id = max(
                val for val in self.contexts.values()) + 1
        if self.command_sequences:
            self.next_command_sequence_id = max(
                val for val in self.command_sequences.values()) + 1

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

    def _add_commmand_sequence(self, command_sequence: CommandSequence) -> int:
        """
        Add a new command sequence and get the corresponding ID.

        If the command sequence already exists, then return its ID.

        Parameters
        ----------
        command_sequence : CommandSequence
            A sequence of commands.

        Returns
        -------
        int
            The ID of the given command sequence.
        """
        try:
            sequence_id = self.command_sequences[command_sequence]
        except KeyError:
            sequence_id = self.next_command_sequence_id
            self.command_sequences[command_sequence] = sequence_id
            self.next_command_sequence_id += 1
        return sequence_id

    def _add_context(self, context: Context) -> int:
        """
        Add a new context and get the corresponding ID.

        Raises
        ------
        KeyError
            If metadata is already stored for the implied context.
        """
        if context in self.contexts:
            raise KeyError(f"Context already exists: {context}")
        next_id = self.next_context_id
        self.contexts[context] = next_id
        self.next_context_id += 1
        return next_id

    def _get_default(self, metadata: ProjectMetadata) -> ProjectMetadata:
        """
        Get the default metadata for the given record.

        In other words, get the metadata with the greatest precedence
        (level) that is less than the given metadata's precedence.

        Parameters
        ----------
        metadata : ProjectMetadata
            A metadata record.

        Returns
        -------
        default : ProjectMetadata
            A default metadata with lower precedence than the given
            record but higher than any other.
        """
        # each metadata overrides the previous, so we only need the
        # last default
        default = None
        for view in metadata.levels(reverse=True, inclusive=False):
            try:
                default = self.get(
                    view.project_name,
                    view.project_url,
                    view.commit_sha,
                    view.coq_version,
                    view.ocaml_version,
                    autofill=False)
            except KeyError:
                pass
            break
        if default is None:
            # fake a default
            default = ProjectMetadata(metadata.project_name, "", [], [], [])
        return default

    def _get(
            self,
            project_name: str,
            project_url: Optional[str],
            commit_sha: Optional[str],
            coq_version: Optional[str],
            ocaml_version: Optional[str],
            metadata: Dict[str,
                           Any]) -> bool:
        """
        Get the metadata for the requested project.

        The metadata is placed in the provided dictionary if not already
        present.

        Parameters
        ----------
        project_name : str
            The name of a project.
        project_url : Optional[str]
            The URL of the project's (Git) repository.
        commit_sha : Optional[str]
            The commit SHA of a revision of the project.
        coq_version : Optional[str]
            The version of Coq against which the project should be
            built.
        ocaml_version : Optional[str]
            The version of the OCaml compiler against which the project
            should be built.
        metadata : Dict[str, Any]
            A dictionary containing keyword arguments to
            `ProjectMetadata`.

        Returns
        -------
        bool
            Whether any metadata exists precisely for the given
            arguments or not.
            That is, if the metadata for the implied `Context` is only
            defined through inheritance from default values, then the
            result will be False.
        """
        context = Context(
            Revision(ProjectSource(project_name,
                                   project_url),
                     commit_sha),
            coq_version,
            ocaml_version)
        try:
            context_id = self.contexts[context]
        except KeyError:
            return False
        for attr in ['build_cmd', 'install_cmd', 'clean_cmd']:
            if attr not in metadata:
                try:
                    metadata[attr] = self.command_sequences.inv[getattr(
                        self,
                        attr)[context_id]].commands
                except KeyError:
                    pass
        for attr in ['serapi_options',
                     'opam_repos',
                     'opam_dependencies',
                     'coq_dependencies',
                     'ignore_path_regex']:
            if attr not in metadata:
                try:
                    metadata[attr] = getattr(self, attr)[context_id]
                except KeyError:
                    pass
        return True

    def get(
            self,
            project_name: str,
            project_url: Optional[str] = None,
            commit_sha: Optional[str] = None,
            coq_version: Optional[Union[str,
                                        Version]] = None,
            ocaml_version: Optional[Union[str,
                                          Version]] = None,
            autofill: Optional[bool] = None) -> ProjectMetadata:
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
        autofill : Optional[bool], optional
            Whether to automatically fill in missing metadata with
            default values (True) or raise an error (False), by default
            equal to ``self.autofill``.

        Returns
        -------
        ProjectMetadata
            The requested metadata.

        Raises
        ------
        KeyError
            If the requested metadata does not exist and autofill is not
            enabled.
        """
        if autofill is None:
            autofill = self.autofill
        if coq_version is not None and not isinstance(coq_version, str):
            coq_version = str(coq_version)
        if ocaml_version is not None and not isinstance(ocaml_version, str):
            ocaml_version = str(ocaml_version)
        temp_metadata = ProjectMetadata(
            project_name,
            "",
            [],
            [],
            [],
            ocaml_version,
            coq_version,
            serapi_version=None,
            project_url=project_url,
            commit_sha=commit_sha)
        metadata_kwargs: Dict[str, Any]
        metadata_kwargs = {
            nm: getattr(temp_metadata,
                        nm) for nm in self._final_fields
        }
        defined = False  # is this metadata undefined (unknown)?
        # retrieve mutable field values, falling back to lower precedent
        # metadata if needed
        for view_i in temp_metadata.levels(reverse=True):
            defined = defined or self._get(
                view_i.project_name,
                view_i.project_url,
                view_i.commit_sha,
                view_i.coq_version,
                view_i.ocaml_version,
                metadata_kwargs)
        # is the metadata completely undefined with no default to fall
        # back upon?
        if not defined:
            if not autofill:
                context = Context(
                    Revision(
                        ProjectSource(project_name,
                                      project_url),
                        commit_sha),
                    coq_version,
                    ocaml_version)
                raise KeyError(
                    f"Unable to retrieve metadata for unknown context: {context}"
                )
            else:
                # autofill required fields
                metadata_kwargs['build_cmd'] = self.default_build_cmd
                metadata_kwargs['install_cmd'] = self.default_install_cmd
                metadata_kwargs['clean_cmd'] = self.default_clean_cmd
                metadata_kwargs['serapi_options'] = self.default_serapi_options
        else:
            # supply defaults if not defined
            metadata_kwargs.setdefault('build_cmd', self.default_build_cmd)
            metadata_kwargs.setdefault('install_cmd', self.default_install_cmd)
            metadata_kwargs.setdefault('clean_cmd', self.default_clean_cmd)
            metadata_kwargs.setdefault(
                'serapi_options',
                self.default_serapi_options)
        return ProjectMetadata(**metadata_kwargs)

    def insert(self, metadata: ProjectMetadata) -> None:
        """
        Insert new metadata into the repository.

        Parameters
        ----------
        metadata : ProjectMetadata
            Metadata for some project.

        Raises
        ------
        KeyError
            If metadata is already stored for the implied context.
        """
        project_source = ProjectSource(
            metadata.project_name,
            metadata.project_url)
        revision = Revision(project_source, metadata.commit_sha)
        context = Context(
            revision,
            metadata.coq_version,
            metadata.ocaml_version)
        context_id = self._add_context(context)
        self.projects.add(metadata.project_name)
        self.project_sources.add(project_source)
        self.revisions.add(revision)
        # only store new data if it overrides all values with lower
        # precedence
        default = self._get_default(metadata)
        for field in fields(ProjectMetadata):
            field_name = field.name
            if field_name not in self._final_fields:
                field_value = getattr(metadata, field.name)
                # Is this a new value?
                if (field_value is not None
                        and field_value != getattr(default,
                                                   field_name)):
                    if field_name in ['build_cmd', 'install_cmd', 'clean_cmd']:
                        sequence = CommandSequence(
                            getattr(metadata,
                                    field_name))
                        sequence_id = self._add_commmand_sequence(sequence)
                        getattr(self, field_name)[context_id] = sequence_id
                    elif field_name in ['opam_repos',
                                        'opam_dependencies',
                                        'coq_dependencies',
                                        'ignore_path_regex']:
                        getattr(self,
                                field_name)[context_id] = set(
                                    getattr(metadata,
                                            field_name))
                    elif field_name == "serapi_options":
                        self.serapi_options[
                            context_id] = metadata.serapi_options

    def serialize(self, fmt: io.Fmt = io.Fmt.yaml) -> Dict[str, Any]:
        """
        Serialize the stored metadata.

        Parameters
        ----------
        fmt : io.Fmt, optional
            The serialization format, by default io.Fmt.yaml

        Returns
        -------
        Dict[str, Any]
            The serialized storage.
        """
        special_fields = {'contexts',
                          'command_sequences'}
        result = {
            f.name: io.serialize(getattr(self,
                                         f.name),
                                 fmt)
            for f in fields(self)
            if f.name not in special_fields
        }
        for f in special_fields:
            result[f] = io.serialize(list(getattr(self, f).items()))
        return result

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'MetadataStorage':
        """
        Deserialize the stored metadata from a dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            The serialized storage as yielded from
            `MetadataStorage.serialize`.

        Returns
        -------
        MetadataStorage
            The deserialized storage.
        """
        special_fields = {'contexts',
                          'command_sequences'}
        field_values = {}
        for f in fields(cls):
            if f.name in data:
                if f.name in special_fields:
                    value = f.type.__origin__(
                        io.deserialize(
                            data[f.name],
                            List[Tuple[f.type.__args__]]))
                else:
                    value = io.deserialize(data[f.name], f.type)
                field_values[f.name] = value
        return cls(**field_values)

    @classmethod
    def dump(
            cls,
            storage: 'MetadataStorage',
            output_filepath: os.PathLike,
            fmt: io.Fmt = io.Fmt.yaml) -> None:
        """
        Serialize metadata and writes to .yml file.

        Parameters
        ----------
        storage : MetadataStorage
            A metadata storage instance.
        output_filepath : os.PathLike
            Filepath to which metadata should be dumped.
        fmt : su.io.Fmt, optional
            Designated format of the output file, by default
            `io.Fmt.yaml`.
        """
        io.dump(output_filepath, storage, fmt=fmt)

    @classmethod
    def load(
            cls,
            filepath: os.PathLike,
            fmt: io.Fmt = io.Fmt.yaml) -> 'MetadataStorage':
        """
        Create list of `ProjectMetadata` objects from input file.

        Parameters
        ----------
        filepath : os.PathLike
            Filepath containing dumped metadata storage.
        fmt : su.io.Fmt, optional
            Designated format of the input file, by default
            `io.Fmt.yaml`.

        Returns
        -------
        MetadataStorage
            A metadata storage instance.
        """
        return io.load(filepath, fmt, serialization=True, clz=MetadataStorage)
