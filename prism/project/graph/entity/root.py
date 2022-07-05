"""
Module for defining Project Node.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from prism.project.metadata.storage import Context

from .base import ProjectEntity


@dataclass
class ProjectRoot(ProjectEntity):
    """
    A node marking the root of a project.
    """

    project_path: Path
    context: Context

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes.
        """
        ProjectEntity.__init__(
            self,
            self.project_path,
        )

    @property
    def commit(self) -> str:
        """
        Return current commit.

        Returns
        -------
        str
            Project name stored in context
        """
        return self.context.revision.commit_sha

    @property
    def project_name(self) -> str:
        """
        Return project name from context.

        Returns
        -------
        str
            Project name stored in context
        """
        return self.context.revision.project_source.project_name

    def id_component(self) -> Tuple[str, str]:
        """
        Use root entity id with relative file path as id.
        """
        return "project", str(self.project_name)

    def init_parent(self) -> None:
        """
        Return None since ProjectRoot has no parent entity.
        """
        return None
