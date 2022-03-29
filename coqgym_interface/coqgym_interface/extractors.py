"""
Module for extracting dataset from targets (projects, files, etc.).
"""
from abc import ABC, abstractmethod
from typing import Dict, Generator, List, Tuple

from git.exc import InvalidGitRepositoryError

from coqgym_interface.dataset import CoqGymBaseDataset
from coqgym_interface.definitions import SentenceFormat
from coqgym_interface.project import ProjectBase, ProjectDir, ProjectRepo


class ExtractorBase(ABC):
    """
    Base Extractor class.
    """

    def __init__(self, targets: List[str]):
        self.targets = targets

    @abstractmethod
    def __iter__(self):
        """
        Return iterator over extracted targets.
        """
        pass


class SentenceExtractorBase(ExtractorBase):
    """
    Base Sentence Extractor class.
    """

    def __init__(self, targets: List[str], sentence_format: SentenceFormat):
        ExtractorBase.__init__(self, targets)
        self.sentence_format = sentence_format


class CoqGymInterfaceSentenceExtractor(SentenceExtractorBase):
    """
    Class to extract sentences using coqgym_interface.
    """

    def __init__(
            self,
            targets: List[str],
            sentence_format: SentenceFormat = SentenceFormat.coq_glom,
            ignore_decode_errors: bool = True):
        SentenceExtractorBase.__init__(self, targets, sentence_format)
        if self.sentence_format is SentenceFormat.coq_glom:
            glom_proofs = True
        else:
            glom_proofs = False
        self.ignore_decode_errors = ignore_decode_errors
        self.glom_proofs = glom_proofs

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
            project = ProjectRepo(
                project_path,
                ignore_decode_errors=self.ignore_decode_errors)
        except InvalidGitRepositoryError:
            project = ProjectDir(
                project_path,
                ignore_decode_errors=self.ignore_decode_errors)
        return project

    def project_dict(self) -> Dict[str, ProjectBase]:
        """
        Return dictionary of ProjectBase instances.

        Returns
        -------
        Dict[str, ProjectBase]:
            ProjectBase instances are keyed by their projects names in
            the returned dictionary.
        """
        project_dict = {}
        for project in self.targets:
            project = self.project(project)
            project_dict[project.name] = project
        return project_dict

    def __iter__(self) -> Generator[None, Tuple[int, str], None]:
        """
        Return a generator of sentence and sentence index.

        Returns
        -------
        Generator[Tuple[int, str]]:
            A generator tjat iteratively return sentence string and
            the string's index as an integer. String index is
            determined by the return order of the generator.
        """
        projects = self.project_dict()
        base_dataset = CoqGymBaseDataset(projects=projects)
        sentences = base_dataset.sentences(
            glom_proofs=self.glom_proofs,
            ignore_decode_errors=self.ignore_decode_errors)
        return enumerate(sentences)
