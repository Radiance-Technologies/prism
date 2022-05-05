"""
Contains all metadata related to paticular GitHub repositories.
"""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import List, Optional

import seutil as su
from radpytools.dataclasses import default_field

EXT_MAP = {
    "json": su.io.Fmt.jsonPretty,
    "json-nosort": su.io.Fmt.jsonNoSort,
    "json_nosort": su.io.Fmt.jsonNoSort,
    "json-min": su.io.Fmt.json,
    "json_min": su.io.Fmt.json,
    "pkl": su.io.Fmt.pkl,
    "yml": su.io.Fmt,
    "yaml": su.io.Fmt.yaml,
    "unknown": su.io.Fmt.text
}


@dataclass(order=True)
class ProjectMetadata:
    """
    Class contains the metadata for a single project.
    """

    project_name: str
    serapi_options: str
    serapi_version: str
    build_cmd: List[str]
    install_cmd: List[str]
    clean_cmd: List[str]
    coq_version: Optional[str] = None
    ignore_path_regex: List[str] = default_field([])
    coq_dependencies: List[str] = default_field([])
    opam_repos: List[str] = default_field([])
    opam_dependencies: List[str] = default_field([])
    project_url: Optional[str] = None
    commit_sha: Optional[str] = None

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
            for projects
        fmt : su.io.Fmt, optional
            Designated format of the output file,
            by default su.io.Fmt.yaml
        """
        su.io.dump(output_filepath, projects, fmt=fmt)

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
        data = su.io.load(filepath, fmt)
        project_metadata: List[ProjectMetadata] = [
            su.io.deserialize(project,
                              cls) for project in data
        ]
        return project_metadata

    @staticmethod
    def infer_formatter(filepath: os.PathLike) -> su.io.Fmt:
        """
        Infer format for loading serialized metadata.

        Use this function to infer a value to pass to the ``fmt``
        argument when using ``ProjectMetadata.loads``.

        Parameters
        ----------
        filepath : os.PathLike
            A filepath to a file containing serialized ProjectMetadata.

        Returns
        -------
        su.io.Fmt
            Seutil formatter to handle loading files based on format.
        """
        extension = os.path.splitext(filepath)[-1].strip(".")
        return EXT_MAP.get(extension, "unknown")
