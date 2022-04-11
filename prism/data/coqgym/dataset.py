"""
Module providing the base dataset object for the CoqGym interface.
"""
import json
import os
import pathlib
import random
from io import TextIOWrapper
from typing import Dict, Generator, List, Optional, Type, TypeVar, Union

from git import InvalidGitRepositoryError

from prism.data.document import CoqDocument
from prism.data.project import (
    DirHasNoCoqFiles,
    ProjectBase,
    ProjectDir,
    ProjectRepo,
)

ProjectDict = Dict[str, Union[ProjectRepo, ProjectDir]]
MetadataDict = TypeVar("MetadataDict")


class Metadata:
    """
    Helper class to load a dataset metadata.

    Attributes
    ----------
    filetype : str
        File format the metadata file is saved in (e.g. json).
    path : str
        Path to metadata file
    data : MetadataDict
        Dictionary format of metadata file.
    """

    def __init__(self, path: Optional[str] = None):
        """
        Initialize Metadata instance.

        Parameters
        ----------
        path: Optional[str]
            File location of metadata file.
        """
        filetype = os.path.splitext(path)[-1][1 :]
        self.filetype = filetype
        self.path = path
        self.data = self._load() if path is not None else None

    def _load(self) -> MetadataDict:
        """
        Load metadata from file and return contents in dict format.
        """
        if self.filetype == 'json':
            data = Metadata.from_json(self.path)
        else:
            raise ValueError(f"Unknown filetype: {self.filetype}")
        return data

    def get_project_split(self) -> Dict[str, str]:
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
        return json.load(open(path))


class CoqGymBaseDataset:
    """
    Base dataset for CoqGym data.

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
            project_class: Optional[Type[ProjectBase]] = None,
            projects: Optional[ProjectDict] = None,
            base_dir: Optional[str] = None,
            dir_list: Optional[List[str]] = None):
        """
        Initialize the CoqGymDataset object.

        Provide exactly one of `projects`, `base_dir`, or `dir_list`.

        Parameters
        ----------
        project_class : Optional[Type[ProjectBase]], optional
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
        dir_list : Optional[List[str]], optional
            If provided, build a `Project` from each of these
            directories. If any of these directories are not
            repositories, an exception is raised, by default None

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
            return (a ^ b ^ c) & ~(a & b & c)

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
            self.projects = projects
        elif base_dir_not_none:
            if project_class is None:
                raise ValueError(
                    "If `base_dir` is given, `project_class` must be "
                    "given as well.")
            for proj_dir in os.listdir(base_dir):
                if os.path.isdir(os.path.join(base_dir, proj_dir)):
                    try:
                        project = project_class(
                            os.path.join(base_dir,
                                         proj_dir))
                        self.projects[project.name] = project
                    except (InvalidGitRepositoryError, DirHasNoCoqFiles):
                        # If we're using ProjectRepo and a directory is
                        # not a repo, or if we're using ProjectDir and
                        # the directory has no Coq files, just ignore it
                        pass
        else:
            if project_class is None:
                raise ValueError(
                    "If `dir_list` is given, `project_class` must be "
                    "given as well.")
            for directory in dir_list:
                try:
                    project = project_class(directory)
                    self.projects[project.name] = project
                except InvalidGitRepositoryError as e:
                    raise ValueError(
                        f"{directory} in `dir_list` is not a valid repository."
                    ) from e
                except DirHasNoCoqFiles as e:
                    raise ValueError(
                        f"{directory} in `dir_list` has no Coq files.") from e
        # Store project weights for sampling later.
        self.weights = {pn: p.size_bytes for pn,
                        p in self.projects.items()}

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
        ignore_decode_errors: bool = False) -> Generator[CoqDocument,
                                                         None,
                                                         None]:
        """
        Yield Coq files from CoqGymBaseDataset.

        Parameters
        ----------
        commit_names : Optional[Dict[str, str]], optional
            The commit (named by branch, hash, or tag) to load from, if
            relevant, for each project, by default None
        ignore_decode_errors : bool
            Skip files with UnicodeDecodeError and ignore the exception
            if True, otherwise raise the exception.

        Yields
        ------
        CoqDocument
            Contents of a Coq file in the group of projects
        """
        if commit_names is None:
            commit_names = {}
        for project_name, project in self.projects.items():
            file_list = project.get_file_list(
                commit_name=commit_names.get(project_name,
                                             None))
            for file in file_list:
                try:
                    with open(file, "r") as f:
                        f: TextIOWrapper
                        contents = f.read()
                        yield CoqDocument(
                            pathlib.Path(file).relative_to(project.path),
                            project_path=project.path,
                            source_code=contents)
                except UnicodeDecodeError as e:
                    if not ignore_decode_errors:
                        raise e

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
        return self.projects[project_name].get_file(
            filename,
            commit_name=commit_name)

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
            commit_name: Optional[str] = None) -> List[str]:
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
            ignore_decode_errors: bool = False) -> Generator[str,
                                                             None,
                                                             None]:
        """
        Yield Coq sentences from CoqGymBaseDataset.

        Parameters
        ----------
        commit_names : Optional[Dict[str, str]], optional
            The commit (named by branch, hash, or tag) to load from, if
            relevant, for each project, by default None
        ignore_decode_errors : bool
            Skip files with UnicodeDecodeError and ignore the exception
            if True, otherwise raise the exception.

        Yields
        ------
        str
            A single sentence, which might be a glommed proof if
            `glom_proofs` is True, from a Coq file within the group of
            projects in the dataset
        """
        coq_file_generator = self.files(
            commit_names,
            ignore_decode_errors=ignore_decode_errors)
        for file_obj in coq_file_generator:
            sentence_list = ProjectBase.split_by_sentence(
                file_obj,
                glom_proofs=glom_proofs)
            for sentence in sentence_list:
                yield sentence
