"""
Common types related to Projects and cached data.
"""

import copy
import re
import subprocess
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple

import networkx as nx
import setuptools_scm

from prism.data.cache.types.command import (
    CommentDict,
    VernacCommandData,
    VernacDict,
    VernacSentence,
)
from prism.project.metadata.dataclass import ProjectMetadata
from prism.util.opam.switch import OpamSwitch
from prism.util.radpytools.path import PathLike
from prism.util.serialize import Serializable


@dataclass
class ProjectBuildResult:
    """
    The result of building a project commit.

    The project environment and metadata are implicit.
    """

    exit_code: int
    """
    The exit code of the project's build command with
    implicit project metadata.
    """
    stdout: str
    """
    The standard output of the commit's build command with
    implicit project metadata.
    """
    stderr: str
    """
    The standard error of the commit's build command with
    implicit project metadata.
    """


@dataclass
class ProjectBuildEnvironment:
    """
    The environment in which a project's commit data was captured.
    """

    switch_config: OpamSwitch.Configuration
    """
    The configuration of the switch in which the commit's build command
    was invoked.
    """
    current_version: str = field(init=False)
    """
    The current version of this package.
    """
    SHA_regex: ClassVar[re.Pattern] = re.compile(r"\+g[0-9a-f]{5,40}")
    """
    A regular expression that matches Git commit SHAs.
    """
    describe_cmd: ClassVar[
        List[str]] = 'git describe --match="" --always --abbrev=40'.split()
    """
    A command that can retrieve the hash of the checked out commit.

    Note that this will fail if the package is installed.
    """

    def __post_init__(self):
        """
        Cache the commit of the coq-pearls repository.
        """
        try:
            self.current_version = setuptools_scm.get_version(
                __file__,
                search_parent_directories=True)
        except LookupError:
            from importlib.metadata import version
            self.current_version = version("coq-pearls")
        match = self.SHA_regex.search(self.current_version)
        self.switch_config = self.switch_config
        if match is not None:
            # replace abbreviated hash with full hash to guarantee
            # the hash remains unambiguous in the future
            try:
                current_commit = subprocess.check_output(
                    self.describe_cmd,
                    cwd=Path(__file__).parent).strip().decode("utf-8")
            except subprocess.CalledProcessError:
                warnings.warn(
                    "Unable to expand Git hash in version string. "
                    "Try installing `coq-pearls` in editable mode.",
                    stacklevel=2)
            else:
                self.current_version = ''.join(
                    [
                        self.current_version[: match.start()],
                        current_commit,
                        self.current_version[match.end():]
                    ])


@dataclass
class ProjectCommitData(Serializable):
    """
    Data associated with a project commit.

    The data is expected to be precomputed and cached to assist with
    subsequent repair mining.
    """

    project_metadata: ProjectMetadata
    """
    Metadata that identifies the project name, commit, Coq version, and
    other relevant data for reproduction and of the cache.
    """
    command_data: VernacDict
    """
    A map from file names relative to the root of the project to the set
    of command results.
    Iterating over the map's keys should follow dependency order of the
    files, i.e., if file ``B`` depends on file ``A``, then ``A`` will
    appear in the iteration before ``B``.
    """
    commit_message: Optional[str] = None
    """
    A description of the changes contained in this project commit.
    """
    comment_data: Optional[CommentDict] = None
    """
    A map from file names relative to the root of the project to a set
    of comments within each file.
    """
    file_dependencies: Optional[Dict[str, List[str]]] = None
    """
    An adjacency list containing the intraproject dependencies of each
    file listed in `command_data`.
    If file ``B`` depends on file ``A``, then ``A`` will appear in
    ``file_dependencies[B]``.
    """
    environment: Optional[ProjectBuildEnvironment] = None
    """
    The environment in which the commit was processed.
    """
    build_result: Optional[ProjectBuildResult] = None
    """
    The result of building the project commit in the `opam_switch` or
    None if building was not required to process the commit.
    """

    def __repr__(self) -> str:
        """
        Get a simple representation that identifies the source of data.
        """
        return ''.join(
            [
                f"ProjectCommitData(project='{self.project_metadata.project_name}', ",
                f"commit_sha='{self.project_metadata.commit_sha}', ",
                f"coq_version='{self.project_metadata.coq_version}', ",
                f"build_result={repr(self.build_result)})"
            ],
        )

    @property
    def commands(self) -> List[Tuple[str, VernacCommandData]]:
        """
        Get all of the commands in the project in canonical order.

        Each command is paired with the name of the file from which it
        originated.
        """
        commands = []
        for filename in self.files:
            commands.extend(
                [(filename,
                  c) for c in self.command_data.get(filename,
                                                    [])])
        return commands

    @property
    def files(self) -> List[str]:
        """
        Return the list of Coq files in the project.

        If `file_dependencies` is set, then the files will be listed in
        dependency order. Otherwise, they will be sorted alphabetically.
        """
        if self.file_dependencies is not None:
            G = nx.DiGraph()
            # sort and reverse in case there are no edges to match
            # output of other branch
            G.add_nodes_from(sorted(self.command_data.keys(), reverse=True))
            for f, deps in self.file_dependencies.items():
                for dep in deps:
                    G.add_edge(f, dep)
            files = [
                k for k in reversed(list(nx.topological_sort(G)))
                if k in self.command_data
            ]
        else:
            files = [k for k in self.command_data.keys()]
            files.sort()
        return files

    @property
    def file_sizes(self) -> Dict[str, int]:
        """
        Get the number of commands in each file in this commit.
        """
        return {
            k: len(v) for k,
            v in self.command_data.items()
        }

    def shallow_copy(self) -> 'ProjectCommitData':
        """
        Get a shallow copy of this structure and its fields.
        """
        return ProjectCommitData(
            copy.copy(self.project_metadata),
            {
                k: v.shallow_copy() for k,
                v in self.command_data.items()
            },
            self.commit_message,
            dict(self.comment_data) if self.comment_data is not None else None,
            dict(self.file_dependencies)
            if self.file_dependencies is not None else None,
            copy.copy(self.environment)
            if self.environment is not None else None,
            copy.copy(self.build_result)
            if self.build_result is not None else None)

    def diff_goals(self) -> None:
        """
        Diff goals in-place, removing consecutive `Goals` of sentences.
        """
        for _, commands in self.command_data.items():
            commands.diff_goals()

    def patch_goals(self) -> None:
        """
        Patch all goals in-place, removing `GoalsDiff`s from sentences.
        """
        for _, commands in self.command_data.items():
            commands.patch_goals()

    def sort_commands(self) -> None:
        """
        Sort the commands of each file in-place.
        """
        for commands in self.command_data.values():
            commands.sort()

    def sorted_sentences(self) -> Dict[str, List[VernacSentence]]:
        """
        Get the sentences of each file sorted by location.

        Returns
        -------
        Dict[str, List[VernacSentence]]
            A map from file names relative to the project root to lists
            of sentences in each file in order of appearance.
        """
        result = {}
        for filename, commands in self.command_data.items():
            result[filename] = commands.sorted_sentences()
        return result

    def write_coq_project(self, dirpath: PathLike) -> None:
        """
        Dump Coq files in the structure of the original project commit.

        Parameters
        ----------
        dirpath : PathLike
            The directory in which to dump the cached commands.
            If the directory does not exist, it will be created.
            Note that any existing files that clash with file names in
            this object will be overwritten.
        """
        # TODO: dump a buildable project
        dirpath = Path(dirpath)
        dirpath.mkdir(parents=True, exist_ok=True)
        for filename, commands in self.command_data.items():
            # filename can contain leading directories
            (dirpath / filename).parent.mkdir(parents=True, exist_ok=True)
            commands.write_coq_file(dirpath / filename)

    def get_coq_project_state(self) -> Dict[str, str]:
        """
        Return Coq project state as a dict of paths and file contents.

        Returns
        -------
        project_dict : Dict[str, str]
            Dictionary mapping a filename to a string
            representation of the file contents.
        """
        project_dict = {}
        for filename, commands in self.command_data.items():
            # filename can contain leading directories
            project_dict[filename] = '\n'.join(commands.stringify())
        return project_dict
