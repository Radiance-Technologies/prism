"""
Contains all metadata related to paticular GitHub repositories.
"""

import os
from dataclasses import dataclass

import seutil as su

METADATA_FIELDS = [
    'full_name',
    'short_name',
    'id',
    'url',
    'sha',
    'tag',
    'dependencies',
    'build_cmd',
    'install_cmd',
    'serapi_options',
    'ignore_path_regex',
    'group'
]


def load_metadata_from_yaml(filepath) -> list:
    """
    Create list of `ProjectMetadata` objects.
    """
    yaml_lst = su.io.load(filepath)

    # Store as list (if only a single project exists in YAML file,
    # seutil.io stores it as a single dict)
    if type(yaml_lst) == dict:
        yaml_lst = [yaml_lst]

    project_metadata = []

    for metadata_dict in yaml_lst:
        missing_fields = [
            field for field in METADATA_FIELDS
            if field not in metadata_dict.keys()
        ]

        # Print if a project in YAML file is missing any
        # required metadata and skip
        if len(missing_fields) > 0:
            print(
                "Missing the following metadata from %s: %s" %
                (metadata_dict['full_name'],
                 ", ".join(missing_fields)))
            continue

        project_metadata.append(
            ProjectMetadata(
                metadata_dict['full_name'],
                metadata_dict['short_name'],
                metadata_dict['id'],
                metadata_dict['url'],
                metadata_dict['sha'],
                metadata_dict['tag'],
                metadata_dict['dependencies'],
                metadata_dict['build_cmd'],
                metadata_dict['install_cmd'],
                metadata_dict['ignore_path_regex'],
                metadata_dict['serapi_options'],
                metadata_dict['group']))
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
