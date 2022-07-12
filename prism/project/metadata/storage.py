"""
Defines central storage/retrieval mechanisms for project metadata.
"""

import os
from dataclasses import dataclass, fields
from functools import partialmethod
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Hashable,
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

from prism.project.metadata.dataclass import ProjectMetadata
from prism.util.opam import OCamlVersion, Version
from prism.util.radpytools.dataclasses import default_field

from .version_info import version_info

T = TypeVar('T')


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

    def as_metadata(self) -> ProjectMetadata:
        """
        Place this context in an otherwise empty metadata record.
        """
        return ProjectMetadata(
            self.revision.project_source.project_name,
            [],
            [],
            [],
            str(self.ocaml_version) if self.ocaml_version is not None else None,
            str(self.coq_version) if self.coq_version is not None else None,
            project_url=self.revision.project_source.repo_url,
            commit_sha=self.revision.commit_sha)

    @classmethod
    def from_metadata(cls, metadata: ProjectMetadata) -> 'Context':
        """
        Create a `Context` corresponding to provided metadata.
        """
        return Context(
            Revision(
                ProjectSource(metadata.project_name,
                              metadata.project_url),
                metadata.commit_sha),
            metadata.coq_version,
            metadata.ocaml_version)


@dataclass(frozen=True)
class CommandSequence:
    """
    A sequence of commands.
    """

    commands: List[str]

    def __hash__(self) -> int:  # noqa: D105
        return hash(tuple(self.commands))


@dataclass(frozen=True)
class IgnorePathRegex:
    """
    Specifies path(s) in a project that should be ignored.
    """

    context: Context
    regex: str


ContextID = int
CommandSequenceID = int
PackageID = int
RepoID = int


@dataclass
class MetadataStorage:
    """
    A central repository for project metadata.

    This class provides storage and retrieval methods for metadata
    across multiple projects and versions. An object of this class
    effectively serves as an in-memory database for project metadata.

    Notes
    -----
    Note that the order of insertion matters when one metadata overrides
    another.
    If the metadata of higher precedence is inserted first, then it will
    not be considered to inherit its metadata from the lower precedence
    version even if identical.
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
    contexts: Dict[Context, ContextID] = default_field(dict())
    # one-to-one overridable fields
    # match metadata field names exactly
    serapi_options: Dict[ContextID, str] = default_field(dict())
    build_cmd: Dict[ContextID, CommandSequenceID] = default_field(dict())
    install_cmd: Dict[ContextID, CommandSequenceID] = default_field(dict())
    clean_cmd: Dict[ContextID, CommandSequenceID] = default_field(dict())
    # one-to-many overridable fields
    # match metadata field names exactly
    opam_repos: Dict[ContextID, Set[RepoID]] = default_field(dict())
    coq_dependencies: Dict[ContextID, Set[PackageID]] = default_field(dict())
    opam_dependencies: Dict[ContextID, Set[PackageID]] = default_field(dict())
    ignore_path_regex: Dict[ContextID, Set[str]] = default_field(dict())
    # meta-metadata
    ocaml_packages: bidict[str, PackageID] = default_field(bidict())
    opam_repositories: bidict[str, RepoID] = default_field(bidict())
    command_sequences: bidict[CommandSequence,
                              CommandSequenceID] = default_field(bidict())
    # incrementable IDs
    # where int = Union[ContextID, PackageID, ...]
    indices: Dict[str, int] = default_field(dict())
    # default fields
    default_coq_version: str = '8.10.2'
    default_serapi_version: str = '8.10.0+0.7.2'
    default_ocaml_version: str = '4.07.2'
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
    _mutable_fields: ClassVar[Set[str]] = {
        f.name for f in fields(ProjectMetadata)
    }.difference(_final_fields)
    """
    Metadata fields that cannot be overridden.
    """
    _bidict_attrs: ClassVar[Dict[str, List[str]]]
    """
    Attributes with indirect storage.
    """
    _bidict_attrs = {
        'command_sequences': ['build_cmd',
                              'install_cmd',
                              'clean_cmd'],
        'opam_repositories': ['opam_repos'],
        'ocaml_packages': ['opam_dependencies',
                           'coq_dependencies']
    }
    _attr_bidicts: ClassVar[Dict[str, str]]
    """
    The inverse map of `_bidict_attrs`.
    """
    _attr_bidicts = {v: k for k,
                     vs in _bidict_attrs.items() for v in vs}

    def __post_init__(self) -> None:
        """
        Bootstrap IDs.
        """
        for index in ['contexts',
                      'command_sequences',
                      'opam_repositories',
                      'ocaml_packages']:
            if getattr(self, index):
                self.indices[index] = max(
                    val for val in getattr(self,
                                           index).values()) + 1
            else:
                self.indices[index] = 0

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

    def _add_to_index(
            self,
            index: str,
            key: T,
            unique: bool = False,
            key_maker: Callable[[T],
                                Hashable] = lambda x: x) -> int:
        """
        Add a new command sequence and get the corresponding ID.

        If the command sequence already exists, then return its ID.

        Parameters
        ----------
        index : str
            Identifies the index that stores data of type `T`.
        key : T
            A key, potentially not directly hashable.
        unique : bool, optional
            Whether the keys must be unique in the index (i.e., one
            cannot add a key that already exists), by default False.
        key_maker : Callable[[T], Hashable]
            A function that transforms the given `key` into a hashable
            type, by default identity.

        Returns
        -------
        int
            The ID of the given `key`.

        Raises
        ------
        KeyError
            If `unique` is True and the key is already present in the
            index.
        """
        key = key_maker(key)
        try:
            sequence_id = getattr(self, index)[key]
        except KeyError:
            sequence_id = self.indices[index]
            getattr(self, index)[key] = sequence_id
            self.indices[index] += 1
        else:
            if unique:
                raise KeyError(f"{index} already exists: {key}")
        return sequence_id

    _add_context = partialmethod(_add_to_index, 'contexts', unique=True)
    """
    Add a new context and get the corresponding ID.

    Raises
    ------
    KeyError
        If metadata is already stored for the implied context.
    """

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
            default = ProjectMetadata(metadata.project_name, [], [], [])
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
            That is, if the metadata for the implied `Context` is not
            defined or is only defined through inheritance from default
            values, then the result will be False.
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
        getters = (lambda x: x.commands, lambda x: x, lambda x: x)
        for (bdct, attrs), accessor in zip(self._bidict_attrs.items(), getters):
            for attr in attrs:
                if attr not in metadata:
                    try:
                        val = getattr(self, attr)[context_id]
                        try:
                            val = accessor(getattr(self, bdct).inv[val])
                        except TypeError:
                            # unhashable collection; map over it
                            val = type(val)(
                                accessor(getattr(self,
                                                 bdct).inv[v]) for v in val)
                        metadata[attr] = val
                    except KeyError:
                        pass
        for attr in ['serapi_options', 'ignore_path_regex']:
            if attr not in metadata:
                try:
                    metadata[attr] = getattr(self, attr)[context_id]
                except KeyError:
                    pass
        return True

    def _insert_field(
            self,
            context_id: int,
            field_name: str,
            field_value: Optional[T],
            default_value: Optional[T]) -> None:
        """
        Insert a field's value for the given context.

        The value is taken from a given metadata and it only actually
        inserted if it differs from the default (i.e., if it overrides
        the default).

        Parameters
        ----------
        context_id : int
            The ID of a metadata record.
        field_name : str
            The name of the field.
        field_value : Optional[T]
            The value to insert for the field
        default_value : Optional[T]
            The default field value.
        """
        if field_name not in self._final_fields:
            # Is this a new value?
            if (field_value is not None and field_value != default_value):
                if field_name in self._attr_bidicts:
                    index = self._attr_bidicts[field_name]
                    if index == 'command_sequences':
                        val = self._add_to_index(
                            index,
                            field_value,
                            key_maker=CommandSequence)
                    else:
                        val = {
                            self._add_to_index(index,
                                               val) for val in field_value
                        }
                    getattr(self, field_name)[context_id] = val
                elif field_name in ['ignore_path_regex']:
                    getattr(self, field_name)[context_id] = set(field_value)
                elif field_name == "serapi_options":
                    self.serapi_options[context_id] = field_value

    def _process_record_args(
        self,
        project_name: Union[str,
                            ProjectMetadata],
        project_url: Optional[str] = None,
        commit_sha: Optional[str] = None,
        coq_version: Optional[Union[str,
                                    Version]] = None,
        ocaml_version: Optional[Union[str,
                                      Version]] = None
    ) -> Tuple[str,
               str,
               str,
               str,
               str]:
        """
        Process record-identifying arguments.

        If the first argument is an instance of `ProjectMetadata`, then
        it is unpacked into the other arguments. Otherwise, the given
        arguments are returned unaffected.
        """
        if isinstance(project_name, ProjectMetadata):
            arg_mask = [
                project_url is not None,
                commit_sha is not None,
                coq_version is not None,
                ocaml_version is not None
            ]
            if any(arg_mask):
                arg_names = [
                    'project_url',
                    'commit_sha',
                    'coq_version',
                    'ocaml_version'
                ]
                raise ValueError(
                    f"{[nm for nm, m in zip(arg_names, arg_mask) if m]} must be None "
                    "if metadata is provided.")
            project_url = project_name.project_url
            commit_sha = project_name.commit_sha
            coq_version = project_name.coq_version
            ocaml_version = project_name.ocaml_version
            project_name = project_name.project_name
        return project_name, project_url, commit_sha, coq_version, ocaml_version

    def _remove_field(self, context_id: int, field_name: str) -> None:
        """
        Remove a field from the indicated record.

        If the field is not explicitly defined for the indicated
        context (it is inherited), then there is no effect.

        Parameters
        ----------
        context_id : int
            The ID of a metadata record.
        field_name : str
            The name of the field.
        """
        if field_name not in self._final_fields:
            getattr(self, field_name).pop(context_id, None)

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
            defined_i = self._get(
                view_i.project_name,
                view_i.project_url,
                view_i.commit_sha,
                view_i.coq_version,
                view_i.ocaml_version,
                metadata_kwargs)
            defined = defined or defined_i
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
        else:
            # supply defaults if not defined
            metadata_kwargs.setdefault('build_cmd', self.default_build_cmd)
            metadata_kwargs.setdefault('install_cmd', self.default_install_cmd)
            metadata_kwargs.setdefault('clean_cmd', self.default_clean_cmd)
        return ProjectMetadata(**metadata_kwargs)

    def get_project_revisions(
            self,
            project_name: str,
            project_url: Optional[str] = None) -> Set[str]:
        """
        Get the set of revisions for a given project.

        Note that this is NOT the complete list of commits that exist
        across all sources for the project but rather just those commits
        that have been assigned unique metadata entries in the storage.

        Parameters
        ----------
        project_name : str
            The name of a project in the storage.
        project_url : Optional[str], optional
            A source URL for the project, by default None.
            If None, then all commits for all sources are returned.

        Returns
        -------
        Set[str]
            A set of commit SHAs for the given project.

        Raises
        ------
        KeyError
            If the project does not possess any metadata.
        """
        if project_name not in self.projects:
            raise KeyError(f"Unknown project: {project_name}")
        return {
            r.commit_sha
            for r in self.revisions
            if r.project_source.project_name == project_name and (
                project_url is None or r.project_source.repo_url == project_url)
            and r.commit_sha is not None
        }

    def get_project_sources(self, project_name: str) -> Set[str]:
        """
        Get the set of repository URLs, if any, for the given project.

        Parameters
        ----------
        project_name : str
            The name of a project in the storage.

        Returns
        -------
        Set[str]
            A set of URLs from which the project may be obtained.

        Raises
        ------
        KeyError
            If the project does not possess any metadata.
        """
        if project_name not in self.projects:
            raise KeyError(f"Unknown project: {project_name}")
        return {
            s.repo_url
            for s in self.project_sources
            if s.project_name == project_name and s.repo_url is not None
        }

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
            self._insert_field(
                context_id,
                field_name,
                getattr(metadata,
                        field_name),
                getattr(default,
                        field_name))

    def populate(
            self,
            metadata: ProjectMetadata,
            autofill: Optional[bool] = None) -> ProjectMetadata:
        """
        Retrieve the fields for the given metadata.

        Equivalent to calling `get` with the project name, url, etc. of
        `metadata`. The provided metadata is not altered.
        """
        return self.get(
            metadata.project_name,
            metadata.project_url,
            metadata.commit_sha,
            metadata.coq_version,
            metadata.ocaml_version,
            autofill)

    def remove(
            self,
            project_name: Union[str,
                                ProjectMetadata],
            project_url: Optional[str] = None,
            commit_sha: Optional[str] = None,
            coq_version: Optional[Union[str,
                                        Version]] = None,
            ocaml_version: Optional[Union[str,
                                          Version]] = None,
            cascade: bool = False) -> None:
        """
        Remove the indicated metadata from storage.

        Parameters
        ----------
        project_name : str or ProjectMetadata
            The name of a project or the metadata to be updated.
            If metadata is provided, its contents are ignored except for
            the purposes of identifying the record.
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
        cascade : bool, optional
            Whether to also remove any more specific metadata that
            overrides the indicated record (True) or to keep such
            metadata in place (False).

        Raises
        ------
        KeyError
            If no such metadata exists.
        ValueError
            If `project_name` is an instance of `ProjectMetadata` and
            any of `project_url`, `commit_sha`, `coq_version`, or
            `ocaml_version` are not None.
        """
        if cascade:
            raise NotImplementedError(
                "Cascaded deletions are not yet supported.")
        (project_name,
         project_url,
         commit_sha,
         coq_version,
         ocaml_version) = self._process_record_args(
             project_name,
             project_url,
             commit_sha,
             coq_version,
             ocaml_version)
        context = Context(
            Revision(ProjectSource(project_name,
                                   project_url),
                     commit_sha),
            coq_version,
            ocaml_version)
        context_id = self.contexts[context]
        for field_name in self._mutable_fields:
            self._remove_field(context_id, field_name)
        self.contexts.pop(context)

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
        special_fields = {
            'contexts',
            'command_sequences',
            'ocaml_packages',
            'opam_repositories'
        }
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

    def update(
            self,
            project_name: Union[str,
                                ProjectMetadata],
            project_url: Optional[str] = None,
            commit_sha: Optional[str] = None,
            coq_version: Optional[Union[str,
                                        Version]] = None,
            ocaml_version: Optional[Union[str,
                                          Version]] = None,
            **kwargs) -> None:
        """
        Update the indicated metadata.

        Parameters
        ----------
        project_name : str or ProjectMetadata
            The name of a project or the metadata to be updated.
            If metadata is provided, its contents are ignored except for
            the purposes of identifying the record.
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
        kwargs : Dict[str, Any]
            New values for fields of the indicated metadata.

        Raises
        ------
        AttributeError
            If an unknown field name is provided in a keyword argument.
        KeyError
            If no such metadata exists.
        ValueError
            If `project_name` is an instance of `ProjectMetadata` and
            any of `project_url`, `commit_sha`, `coq_version`, or
            `ocaml_version` are not None.
        """
        (project_name,
         project_url,
         commit_sha,
         coq_version,
         ocaml_version) = self._process_record_args(
             project_name,
             project_url,
             commit_sha,
             coq_version,
             ocaml_version)
        if kwargs:
            context = Context(
                Revision(ProjectSource(project_name,
                                       project_url),
                         commit_sha),
                coq_version,
                ocaml_version)
            metadata = context.as_metadata()
            try:
                context_id = self.contexts[context]
            except KeyError:
                is_implied = False
                for view in metadata.levels(reverse=True, inclusive=False):
                    if Context.from_metadata(view) in self.contexts:
                        # this metadata is implied to exist
                        is_implied = True
                        # create an explicit record of it
                        context_id = self._add_context(context)
                        break
                if not is_implied:
                    raise
            default = self._get_default(metadata)
            for field_name, field_value in kwargs.items():
                self._remove_field(context_id, field_name)
                self._insert_field(
                    context_id,
                    field_name,
                    field_value,
                    getattr(default,
                            field_name))

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
        special_fields = {
            'contexts',
            'command_sequences',
            'ocaml_packages',
            'opam_repositories'
        }
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
