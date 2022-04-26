"""
Contains all metadata related to paticular GitHub repositories.
"""

import os
from dataclasses import dataclass
from typing import List

import seutil as su


def load_metadata_from_yaml(filepath) -> list:
    """
    Create list of `ProjectMetadata` objects.
    """
    data = su.io.load(filepath, su.io.Fmt.yaml)
    project_metadata: List[ProjectMetadata] = [
        su.io.deserialize(project,
                          ProjectMetadata)
        for project in data
        if set(project.keys()) == set(ProjectMetadata.__dataclass_fields__)
    ]

    return project_metadata


@dataclass(order=True)
class ProjectMetadata:
    """
    Class containing the metadata for a single project.
    """

    full_name: str
    short_name: str
    id: str
    url: str
    sha: str
    tag: str
    dependencies: list
    build_cmd: str
    install_cmd: str
    ignore_path_regex: str
    serapi_options: str
    group: str

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
