"""
Module providing Coq project directory class representations.
"""
import os
import pathlib

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
