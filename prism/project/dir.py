"""
Module providing Coq project directory class representations.
"""
import os
import pathlib
import warnings
from typing import List

from prism.data.document import CoqDocument
from prism.language.gallina.parser import CoqParser
from prism.project.base import MetadataArgs, Project
from prism.project.exception import DirHasNoCoqFiles


class ProjectDir(Project):
    """
    Class for representing a Coq project.

    This class makes no assumptions about whether the project directory
    is a git repository or not.
    """

    def __init__(self, dir_abspath: os.PathLike, *args, **kwargs):
        """
        Initialize Project object.
        """
        self.working_dir = dir_abspath
        super().__init__(dir_abspath, *args, **kwargs)
        if not self._traverse_file_tree():
            raise DirHasNoCoqFiles(f"{dir_abspath} has no Coq files.")

    @property
    def metadata_args(self) -> MetadataArgs:  # noqa: D102
        return MetadataArgs(None, None, self.coq_version, self.ocaml_version)

    @property
    def name(self) -> str:  # noqa: D102
        return pathlib.Path(self.working_dir).stem

    @property
    def path(self) -> os.PathLike:  # noqa: D102
        return self.working_dir

    def _get_file(self, filename: str, *args, **kwargs) -> CoqDocument:
        """
        Get specific Coq file and return the corresponding CoqDocument.

        Parameters
        ----------
        filename : str
            The absolute path to the file

        Returns
        -------
        CoqDocument
            The corresponding CoqDocument

        Raises
        ------
        ValueError
            If given `filename` does not end in ".v"

        Warns
        -----
        UserWarning
            If either of `args` or `kwargs` is nonempty.
        """
        if args or kwargs:
            warnings.warn(
                f"Unexpected additional arguments to Project[{self.name}]._get_file.\n"
                f"    args: {args}\n"
                f"    kwargs: {kwargs}")
        return CoqDocument(
            pathlib.Path(filename).relative_to(self.path),
            project_path=self.path,
            source_code=CoqParser.parse_source(filename))

    def _pre_get_file(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _pre_get_random(self, **kwargs):
        """
        Do nothing.
        """
        pass

    def _traverse_file_tree(self) -> List[CoqDocument]:
        """
        Traverse the file tree and return a list of Coq file objects.
        """
        files = pathlib.Path(self.working_dir).rglob("*.v")
        out_files = []
        for file in files:
            out_files.append(
                CoqDocument(
                    file.relative_to(self.path),
                    project_path=self.path,
                    source_code=CoqParser.parse_source(file)))
        return out_files
