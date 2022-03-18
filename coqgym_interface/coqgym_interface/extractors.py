"""
Module for extracting dataset from targets (projects, files, etc.).
"""
from typing import Dict, Generator, List, Tuple

import datasets
from git.exc import InvalidGitRepositoryError

from coqgym_interface.dataset import CoqGymBaseDataset
from coqgym_interface.definitions import SentenceFormat
from coqgym_interface.project import ProjectDir, ProjectRepo


class ExtractorBase(ABC):
    """
    Base Extractor class.
    """
    def __init__(self, targets: List[str]):
        self.targets = targets

    @abstractmethod
    def __iter__(self):
        pass


class SentenceExtractorBase(Extractor):
    """
    Base Sentence Extractor class.
    """
    def __init__(self, targets: List[str], sentence_format: SentenceFormat):

        super().__init__(self, targets)
        self.sentence_format = sentence_format


class CoqGymInterfaceSentenceExtractor(SentenceExtractorBase):
    """
    Class to extract sentences using coqgym_interface.
    """
    def __init__(
        self,
        *args,
        ignore_decode_errors: bool = True,
        **kwargs
    ):
        super().__init__(self, *args, **kwargs)
        if self.sentence_format is SentenceFormat.coq_gloom
            gloom_proofs = True
        else
            gloom_proofs = False
        self.ignore_decode_errors = ignore_decode_errors
        self.gloom_proofs = gloom_proofs

    def project(self, project_path: str) -> ProjectBase:
        """
        Generate ProjectBase from project root directory path.

        Parameters
        ----------
        project_path : str
            Path to project directory or repo directory.

        Returns
        -------
        ProjectBase
            An interface to extract sentences from a project.
        """
        try:
            project = ProjectRepo(project_path, self.ignore_decode_errors=True)
        except InvalidGitRepositoryError:
            project = ProjectDir(project_path, self.ignore_decode_errors=True)
        return project

    def project_dict(self) -> Dict[str, ProjectBase]:
        """
        Return dictionary of ProjectBase instances.
        """
        project_dict = {}
        for project in projects:
            project = self.project(project)
            project_dict[project.name] = project
        return project_dict

    def __iter__(self) -> Generator[Tuple[int, str]]:
        """
        Return a generator of sentence and sentence index.
        """
        projects = self.project_dict()
        base_dataset = CoqGymBaseDataset(projects=projects)
        sentences = base_dataset.sentences(
            gloom_proofs=self.gloom_proofs,
            ignore_decode_errors=self.ignore_decode_errors)
        return enumerate(sentences)
