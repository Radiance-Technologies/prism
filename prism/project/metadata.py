"""
Contains all metadata related to paticular GitHub repositories.
"""

import os
from dataclasses import dataclass, fields
from typing import List, Optional

import seutil as su


def load_metadata_from_yaml(filepath) -> list:
    """
    Create list of `ProjectMetadata` objects.
    """
    data = su.io.load(filepath, su.io.Fmt.yaml)
    project_metadata: List[ProjectMetadata] = [
        su.io.deserialize(project,
                          ProjectMetadata) for project in data
    ]

    return project_metadata


@dataclass(order=True)
class ProjectMetadata:
    """
    Class contains the metadata for a single project.
    """

    project_name: str = None
    project_url: str = None
    serapi_options: str = None
    coq_version: List[str] = None
    serapi_version: List[str] = None
    build_cmd: str = None
    opam_repos: Optional[List[str]] = None
    commit_sha: Optional[str] = None
    ignore_path_regex: Optional[List[str]] = None
    install_cmd: Optional[str] = None
    clean_cmd: Optional[str] = None

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

    def serialize_to_file(self, output_filepath: os.PathLike) -> None:
        """
        Serialize metadata and writes to .yml file.

        Parameters
        ----------
        output_filepath : os.PathLike
            The path of the file to which the metadata will be written.
        """
        # Manual bypass for writing multiple projects to an existing
        # file since seutil.io doesn't support this feature for YAML
        if not os.path.isfile(output_filepath):
            su.io.dump(output_filepath, [self], fmt=su.io.Fmt.yaml)
        else:
            # Serialize
            serialized = su.io.serialize([self], fmt='yaml')

            # Write to file
            with open(output_filepath, 'a') as output_file:
                output_file.write("\n")
                su.io.Fmt.yaml.writer(output_file, serialized)
