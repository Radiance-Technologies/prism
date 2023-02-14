"""
Module providing the base dataset object for Coq projects.
"""
import json
import os
import random
import typing
from typing import Dict, Generator, Iterable, Optional, Tuple, Type

from git import InvalidGitRepositoryError

from prism.data.document import CoqDocument
from prism.language.heuristic.parser import CoqSentence
from prism.project import DirHasNoCoqFiles, Project, ProjectRepo
from prism.project.metadata.storage import MetadataStorage

ProjectDict = Dict[str, Project]
MetadataDict = dict


class DatasetMetadata:
    """
    Helper class to load a dataset metadata.

    Parameters
    ----------
    path: Optional[str]
        File location of metadata file.
    """

    def __init__(self, path: str = ""):
        """
        Initialize Metadata instance.
        """
        filetype = os.path.splitext(path)[-1][1 :]
        self.filetype = filetype
        """
        File format the metadata file is saved in (e.g. json).
        """
        self.path = path
        """
        Path to metadata file.
        """
        self.data = self._load() if path is not None else None
        """
        Dictionary representation of metadata file.
        """

    def _load(self) -> MetadataDict:
        """
        Load metadata from file and return contents in dict format.
        """
        if self.filetype == 'json':
            data = DatasetMetadata.from_json(self.path)
        else:
            raise ValueError(f"Unknown filetype: {self.filetype}")
        return data

    def get_project_split(self) -> Optional[Dict[str, str]]:
        """
        Return dictionary map of split names to project names.

        Each split present ('train', 'test', 'validation') maps to a
        list of project names. All files in a project will be used to
        generate examples for the corresponding split.
        """
        return self.data['split'] if self.data else None

    @staticmethod
    def from_json(path: str) -> MetadataDict:
        """
        Load a json from given the filename.
        """
        with open(path) as f:
            return json.load(f)


class CoqProjectBaseDataset:
    """
    Base dataset for Coq data spread across multiple projects.

    Attributes
    ----------
    projects : ProjectDict
        The dictionary of Coq projects to draw data from
    weights : Dict[str, float]
        Weights for each project for sampling

    Methods
    -------
    files(commit_names)
        Returns a generator that yields Coq files from the object.
    get_random_file(project_name, commit_name)
        Returns a random Coq source file from one of the internal
        projects.
    get_file(filename, project_name, commit_name)
        Returns a specific Coq source file from a specific project and
        commit (if applicable).
    get_random_sentence(filename, project_name, glom_proofs,
            commit_name)
        Returns a random sentence from one of the internal projects.
    get_random_sentence_pair_adjacent(filename, project_name,
            glom_proofs, commit_name)
        Returns a random adjacent sentence pair from one of the internal
        projects.
    sentences(commit_names, glom_proofs)
        Returns a generator that yields Coq sentences from the object.
    """

    projects: ProjectDict = {}

    def __init__(
            self,
            *,
            project_class: Optional[Type[Project]] = None,
            projects: Optional[ProjectDict] = None,
            base_dir: Optional[str] = None,
            dir_list: Optional[Iterable[str]] = None,
            metadata_storage: Optional[MetadataStorage] = None,
            **project_class_kwargs):
        """
        Initialize the `CoqProjectDataset` object.

        Provide exactly one of `projects`, `base_dir`, or `dir_list`.

        Parameters
        ----------
        project_class : Optional[Type[Project]], optional
            Class name for Project objects. Either ProjectRepo or
            ProjectDir. Must be given if `base_dir` or `dir_list` is
            given. Ignored if `projects` is given.
        projects : Optional[ProjectDict], optional
            If provided, use these already-created `Project` objects to
            build the dataset, by default None
        base_dir : Optional[str], optional
            If provided, build `Project` objects from the subdirectories
            in this directory. Any subdirectories that are not
            repositories are ignored, by default None
        dir_list : Optional[Iterable[str]], optional
            If provided, build a `Project` from each of these
            directories. If any of these directories are not
            repositories, an exception is raised, by default None
        metadata_storage : Optional[MetadataStorage], optional
            Required if either base_dir or dir_list are provided.
            Serves as the default `MetadataStorage` to any
            internally created `Project`.

        Raises
        ------
        ValueError
            If != 1 of the input arguments are provided
        ValueError
            If one or more of the directories in `dir_list` is not a
            repository
        ValueError
            If `project_class` is not provided and either `base_dir` or
            `dir_list` is provided.
        """

        def _three_way_xor(a: bool, b: bool, c: bool) -> bool:
            return bool((a ^ b ^ c) & ~(a & b & c))

        projects_not_none = projects is not None
        base_dir_not_none = base_dir is not None
        dir_list_not_none = dir_list is not None
        if not _three_way_xor(projects_not_none,
                              base_dir_not_none,
                              dir_list_not_none):
            raise ValueError(
                "Provide exactly one of the input arguments"
                " `projects`, `base_dir`, or `dir_list`.")
        if projects_not_none:
            self.projects = typing.cast(ProjectDict, projects)
        elif base_dir_not_none:
            self._init_projects_base_dir(
                project_class,
                base_dir,
                metadata_storage,
                project_class_kwargs)
        else:
            self._init_projects_dir_list(
                project_class,
                dir_list,
                metadata_storage,
                project_class_kwargs)
        # Store project weights for sampling later.
        self.weights = {
            pn: p.size_bytes for pn,
            p in self.projects.items()
        }
        self.sentence_extraction_method = next(
            iter(self.projects.values())).sentence_extraction_method

    def _init_projects_base_dir(
            self,
            project_class,
            base_dir,
            metadata_storage,
            project_class_kwargs):
        """
        Initialize Project dictionary using a base directory.
        """
        if project_class is None:
            raise ValueError(
                "If `base_dir` is given, `project_class` must be "
                "given as well.")
        if metadata_storage is None:
            raise ValueError(
                "If `base_dir` is given, `metadata_storage` must "
                "be given as well.")
        for proj_dir in os.listdir(base_dir):
            if os.path.isdir(os.path.join(base_dir, proj_dir)):
                try:
                    project = project_class(
                        os.path.join(base_dir,
                                     proj_dir),
                        metadata_storage=metadata_storage,
                        **project_class_kwargs)
                    self.projects[project.name] = project
                except (InvalidGitRepositoryError, DirHasNoCoqFiles):
                    # If we're using ProjectRepo and a directory is
                    # not a repo, or if we're using ProjectDir and
                    # the directory has no Coq files, just ignore it
                    pass

    def _init_projects_dir_list(
            self,
            project_class,
            dir_list,
            metadata_storage,
            project_class_kwargs):
        """
        Initialize Project dictionary using a directory list.
        """
        if project_class is None:
            raise ValueError(
                "If `dir_list` is given, `project_class` must be "
                "given as well.")
        if metadata_storage is None:
            raise ValueError(
                "If `dir_list` is given, `metadata_storage` must "
                "be given as well.")
        for directory in dir_list:
            try:
                project = project_class(
                    directory,
                    metadata_storage=metadata_storage,
                    **project_class_kwargs)
                self.projects[project.name] = project
            except InvalidGitRepositoryError as e:
                raise ValueError(
                    f"{directory} in `dir_list` is not a valid repository."
                ) from e
            except DirHasNoCoqFiles as e:
                raise ValueError(
                    f"{directory} in `dir_list` has no Coq files.") from e

    def _get_random_project(self) -> str:
        """
        Get a random project from the dataset's internal selection.

        The selection is weighted by ``self.weights``.

        Returns
        -------
        str
            The name of a randomly chosen project.
        """
        weights = []
        project_names = list(self.projects.keys())
        for proj in project_names:
            weights.append(self.weights[proj])
        chosen_proj = random.choices(project_names, weights, k=1)[0]
        return chosen_proj

    def files(
        self,
        commit_names: Optional[Dict[str,
                                    str]] = None,
    ) -> Generator[CoqDocument,
                   None,
                   None]:
        """
        Yield Coq files from `CoqProjectBaseDataset`.

        Parameters
        ----------
        commit_names : Optional[Dict[str, str]], optional
            The commit (named by branch, hash, or tag) to load from, if
            relevant, for each project, by default None

        Yields
        ------
        CoqDocument
            Contents of a Coq file in the group of projects
        """
        if commit_names is None:
            commit_names = {}
        for project_name, project in self.projects.items():
            commit_name = commit_names.get(project_name, None)
            kwargs = {}
            if commit_name is not None:
                if not isinstance(project, ProjectRepo):
                    raise ValueError(
                        f"Cannot checkout commit from non-Git project {project_name}"
                    )
                kwargs['commit_name'] = commit_name
            file_list = project.get_file_list(**kwargs)
            for file in file_list:
                yield project.get_file(file)

    def get_random_file(
            self,
            project_name: Optional[str] = None,
            commit_name: Optional[str] = None) -> CoqDocument:
        """
        Return a random Coq source file from one of the projects.

        The commit and project may be specified or left to be chosen at
        random.

        Parameters
        ----------
        project_name : Optional[str], optional
            Project name to draw random file from, by default None
        commit_name : Optional[str], optional
            Commit hash, branch name, or tag name to draw random file
            from, if used by `project_class`, by default None

        Returns
        -------
        CoqDocument
            A random Coq source file in the form of a CoqDocument
        """
        if project_name is None:
            project_name = self._get_random_project()
        return self.projects[project_name].get_random_file(
            commit_name=commit_name)

    def get_file(
            self,
            filename: str,
            project_name: str,
            commit_name: str = 'master') -> CoqDocument:
        """
        Return specific Coq source file from specific project & commit.

        Parameters
        ----------
        filename : str
            The absolute path to the file to return
        project_name : str
            Project name from which to load the file
        commit_name : str, optional
            A commit hash, branch name, or tag name from which to fetch
            the file, if used by `project_class`, by default 'master'

        Returns
        -------
        CoqDocument
            A CoqDocument corresponding to the selected Coq source file
        """
        project = self.projects[project_name]
        kwargs = {}
        if commit_name is not None:
            if not isinstance(project, ProjectRepo):
                raise ValueError(
                    f"Cannot checkout commit from non-Git project {project_name}"
                )
            kwargs['commit_name'] = commit_name
        return project.get_file(filename, **kwargs)

    def get_random_sentence(
            self,
            filename: Optional[str] = None,
            project_name: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> str:
        """
        Return a random sentence from the group of projects.

        Filename, project name, and commit are random unless they are
        provided.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentence from, by default None
        project_name : Optional[str], optional
            Project name from which to load the file, by default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseudo-sentences, by default True
        commit_name : Optional[str], optional
            A commit hash, branch name, or tag name from which to fetch
            the file, if used by `project_class`, by default None

        Returns
        -------
        str
            A random sentence from the group of projects
        """
        if project_name is None:
            project_name = self._get_random_project()
        return self.projects[project_name].get_random_sentence(
            filename,
            glom_proofs,
            commit_name=commit_name)

    def get_random_sentence_pair_adjacent(
            self,
            filename: Optional[str] = None,
            project_name: Optional[str] = None,
            glom_proofs: bool = True,
            commit_name: Optional[str] = None) -> Tuple[str,
                                                        str]:
        """
        Return a random adjacent sentence pair from the projects.

        Parameters
        ----------
        filename : Optional[str], optional
            Absolute path to file to load sentences from, by default
            None
        project_name : Optional[str], optional
            Project naem from which to load the sentence pair, by
            default None
        glom_proofs : bool, optional
            Boolean flag indicating whether proofs should form their own
            pseduo-sentences, by default True
        commit_name : Optional[str], optional
            Commit hash, branch name, or tag name from which to fetch
            the sentence pair, by default None

        Returns
        -------
        List[str]
            A list of two adjacent sentences from the projects, with the
            first sentence chosen at random
        """
        if project_name is None:
            project_name = self._get_random_project()
        return self.projects[project_name].get_random_sentence_pair_adjacent(
            filename,
            glom_proofs,
            commit_name=commit_name)

    def sentences(
        self,
        commit_names: Optional[Dict[str,
                                    str]] = None,
        glom_proofs: bool = True,
        glom_ltac: bool = False,
        return_asts: bool = False,
        skip_file_errors: bool = False,
        skip_sentence_errors: bool = False) -> Generator[CoqSentence,
                                                         None,
                                                         None]:
        """
        Yield Coq sentences from `CoqProjectBaseDataset`.

        Parameters
        ----------
        commit_names : Optional[Dict[str, str]], optional
            The commit (named by branch, hash, or tag) to load from, if
            relevant, for each project, by default None
        skip_file_errors : bool, optional
            If True, ignore errors on a per-file basis,
            otherwise raise the exception.
        skip_sentence_errors : bool, optional
            If True, return list of sentences that were successfully
            parsed while ignoring sentences where an exception was
            raised, otherwise raise the exception.

        Yields
        ------
        CoqSentence
            A single sentence, which might be a glommed proof if
            `glom_proofs` is True, from a Coq file within the group of
            projects in the dataset
        """
        for project in self.projects.values():
            for filename in project.get_file_list():
                try:
                    sentence_list = project.get_sentences(
                        filename,
                        glom_proofs=glom_proofs,
                        glom_ltac=glom_ltac,
                        return_asts=return_asts,
                        sentence_extraction_method=self
                        .sentence_extraction_method,
                        skip_sentence_errors=skip_sentence_errors)
                except Exception as exc:
                    if skip_file_errors:
                        continue
                    raise exc
                for sentence in sentence_list:
                    yield sentence
