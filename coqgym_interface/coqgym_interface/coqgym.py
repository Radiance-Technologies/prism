import json
import os
from enum import Enum
from typing import Dict, List, NewType, Optional, Sequence, Tuple, Union

import datasets
from git.exc import InvalidGitRepositoryError

from coqgym_interface.dataset import CoqGymBaseDataset, Metadata
from coqgym_interface.extractors import (
    CoqGymInterfaceSentenceExtractor,
    Extractor,
)
from coqgym_interface.HFDatasets.definitions import (
    COQGYM_ENV_VAR,
    DEFAULT_METADATA_FILENAME,
    DatasetTask,
    SentenceFormat,
)
from coqgym_interface.project import ProjectDir, ProjectRepo

logger = datasets.logging.get_logger(__name__)




class CoqGymConfig(datasets.BuilderConfig):
    """
    BuilderConfig for Coq dataset.
    """

    def __init__(
        self,
        data_path: Optional[str] = None,
        extractor_cls: Optional[Extractor] = None,
        features: List[str] = ["text"],
        label_classes: Optional[Sequence[str]] = None,
        metadata_path: Optional[str] = None,
        sentence_format: Union[str, SentenceFormat] = SentenceFormat.coq_gloom,
        task: Union[str, DatasetTask] = DatasetTask.LM,
        task_version: Optional[str] = None,
        **kwargs
    ):
        """
        BuilderConfig for Coq dataset.
        Parameters
        ----------
        data_path : Optional[str]
            Path to dataset files.
        features : List[str]
            List of feature names
        label_classes : Optional[Sequence[str]]
            List of optional label class names.
        metadata_path : Optional[str]
            Path to metadata file.
        sentence_format : Union[str, SentenceFormat]
            Enumerated value identifying how sentences are formatted.
        task : Union[str, DatasetTask]
            Task name for dataset.
        task_version : Optional[str]
            For different ways generate a dataset for the same task,
            this string can be used as way to distinguish between said
            tasks.
        """
        # Defaults for path variables
        if data_path is None:
            data_path = os.environ[COQGYM_ENV_VAR]
        if metadata_path is None:
            metadata_path = os.path.join(data_path, DEFAULT_METADATA_FILENAME)

        # Cast to Enum types
        if isinstance(task, str):
            task = DatasetTask(task)
        if isinstance(sentence_format, str):
            sentence_format = SentenceFormat(sentence_format)

        # Construct default name if None given.
        if kwargs.get('name', None) is None:
            # Get task as a string
            task_str = task.value
            if task_version:
                task_str = '_'.join((task_str, task_version))
            # Get sentence format as string
            sentence_str = sentence_format.value
            # Construct name based on options.
            kwargs['name'] = '_'.join(('coqgym', task_str, sentence_str))

        super().__init__(
            version=datasets.Version(
                "1.0.0",
            ),
            **kwargs
        )
        self.data_path = data_path
        self.extractor_cls = extractor_cls
        self.features = features
        self.label_classes = label_classes
        self.metadata_path = metadata_path
        self.task = task
        self.task_version = task_version
        self.sentence_format = sentence_format


class CoqGym(datasets.GeneratorBasedBuilder):

    VERSION = datasets.Version("0.1.0")

    BUILDER_CONFIGS = [
        CoqGymConfig(  # Sentence per line, with proof gloom
            extractor_cls = CoqGymInterfaceSentenceExtractor,
            features=["text"],
            name="coqgym-coqlang-gloomed",
            sentence_format='coq-gloom',
            task='language-modeling',
            task_version="pretraining-phase1",
            description="MLM with coq code. 1 sentence per line, proofs are 1 sentence"
        ),
        CoqGymConfig(  # Sentence per line, no gloom
            extractor_cls = CoqGymInterfaceSentenceExtractor,
            features=["text"],
            sentence_format='coq',
            task='language-modeling',
            task_version="pretraining-phase1",
            description="MLM with coq code. 1 sentence per line"
        ),
    ]

    DEFAULT_CONFIG_NAME: str = "coqgym-coqlang-gloomed"

    def _coqgym_interface_extractor(self, targets: List[str], split: datasets.Split) -> :
        if self.config.task is DatasetTask.LM:
            CoqGymInterfaceSentenceExtractor(target_paths)


    def _info(self) -> datasets.DatasetInfo:
        """
        Generate Dataset Info for Coq Dataset.
        """
        features = {feature: datasets.Value("string") for feature in self.config.features}
        return datasets.DatasetInfo(
            description=self.config.description,
            features=datasets.Features(features)
        )

    def _split_generators(self, dl_manager: datasets.DownloadManager) -> List[datasets.SplitGenerator]:
        """
        Create SplitGenerator for each split inside metadata file.
        """
        metadata = Metadata(self.config.metadata_path)
        split_dict = metadata.get_project_split()
        return [
            datasets.SplitGenerator(
                name=datasets.Split(split.lower()),
                gen_kwargs={
                    "targets": targets,
                    "split": datasets.Split(split.lower())
                }
            ) for split, targets in split_dict.items()
        ]

    def _generate_examples(self, targets: List[str], split: datasets.Split):
        """
        Yield examples in language modeling format from targets.
        """
        if self.config.task is DatasetTask.LM:
            data_path = self.config.data_path
            target_paths = [os.path.join(data_path, t) for t in targets]
            sentence_extractor = self.config.extractor_cls(
                target_paths,
                sentence_format=self.sentence_format,
                ignore_decode_errors=self.ignore_decode_errors
            )
            base_dataset = _get_coqgym_dataset(self.config.data_path, targets)
            for id_, sentence in enumerate(base_dataset.sentences()):
                if sentence.strip():
                    yield id_, {"text": sentence}
                else:
                    yield id_, {"text": ""}
        else:
            raise ValueError(f"Unknown or unimplemented task: {self.config.task}")

def _get_coqgym_dataset(root: str, projects: List[str]) -> CoqGymBaseDataset:

    def make(cls):
        d = {}
        for dir in projects:
            project = cls(os.path.join(root, dir), ignore_decode_errors=True)
            d[project.name] = project
        return d
    #try:
    #    base_dataset = CoqGymBaseDataset(projects=make(ProjectRepo))
    #except InvalidGitRepositoryError:
    #    base_dataset = CoqGymBaseDataset(projects=make(ProjectDir))
    base_dataset = CoqGymBaseDataset(projects=make(ProjectDir))
    return base_dataset
