"""
Contains all metadata related to paticular GitHub repositories.
"""

import os
from collections import Iterable
from dataclasses import dataclass, fields
from typing import List, Optional

import seutil as su


@dataclass(order=True)
class ProjectMetadata:
    """
    Class contains the metadata for a single project.
    """

    project_name: str = None
    serapi_options: str = None
    coq_version: str = None
    serapi_version: str = None
    ignore_path_regex: List[str] = None
    coq_dependencies: List[str] = None
    build_cmd: List[str] = None
    install_cmd: List[str] = None
    clean_cmd: List[str] = None
    opam_repos: List[str] = None
    opam_dependencies: List[str] = None
    project_url: Optional[str] = None
    commit_sha: Optional[str] = None

    def __post_init__(self) -> None:
        """
        Raise exception if required fields missing.
        """
        missing_required_fields = [
            field.name for field in fields(self) if
            field.type != Optional[field.type] and getattr(self,
                                                           field.name) is None
        ]
        if len(missing_required_fields) > 0:
            raise TypeError(
                "Missing following required field(s): %s"
                % ", ".join(missing_required_fields))

    @classmethod
    def dump(
            cls,
            projects: Iterable['ProjectMetadata'],
            output_filepath: os.PathLike,
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> None:
        """
        Serialize metadata and writes to .yml file.

        Parameters
        ----------
        projects : Iterable[ProjectMetadata]
            List of `ProjectMetadata` class objects to be serialized
        output_filepath : os.PathLike
            Filepath of YAML file to be written containing metadata
            for 1+ projects
        fmt : su.io.Fmt, optional
            Designated format of the output file,
            by default su.io.Fmt.yaml
        """
        # Manual bypass for writing multiple projects to an existing
        # file since seutil.io doesn't support this feature for YAML
        if not os.path.isfile(output_filepath):
            su.io.dump(output_filepath, projects, fmt=fmt)
        else:
            # Serialize
            serialized = su.io.serialize(projects, fmt=fmt)

            # Write to file
            with open(output_filepath, 'a') as output_file:
                fmt.writer(output_file, serialized)

    @classmethod
    def load(cls,
             filepath: os.PathLike,
             fmt: su.io.Fmt = su.io.Fmt.yaml) -> List['ProjectMetadata']:
        """
        Create list of `ProjectMetadata` objects from input file.

        Parameters
        ----------
        filepath : os.PathLike
            Filepath of YAML file containing project metadata
        fmt : su.io.Fmt, optional
            Designated format of the input file,
            by default su.io.Fmt.yaml

        Returns
        -------
        List[ProjectMetadata]
            List of `ProjectMetadata` objects
        """
        data = su.io.load(filepath, su.io.Fmt.yaml)
        project_metadata: List[ProjectMetadata] = [
            su.io.deserialize(project,
                              ProjectMetadata) for project in data
        ]

        return project_metadata
