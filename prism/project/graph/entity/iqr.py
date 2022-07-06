"""
Module defining node for extract IQR flags.
"""
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Tuple, TypeVar, Union

from prism.project.graph.entity.base import ProjectEntity

from .file import ProjectFile
from .logical import LogicalName

IQR_FLAG = Literal["I", "Q", "R"]
"""
The letter value of argument for a project's IQR arguments.
"""
IQR_PHYSICAL_PATH = TypeVar('IQR_PHYSICAL_PATH')
"""
Path passed as first of two arguments -Q and -R and only
argument passed to -I.
"""
IQR_BOUND_NAME = TypeVar('IQR_BOUND_NAME')
"""
Name passed as second argument -R and -Q that deteremines
access of libraries found in subdirectory(ies) of
first argument to -R and -Q.
"""
IQR_BINDING_ARGUMENT = Tuple[IQR_PHYSICAL_PATH, IQR_BOUND_NAME]
"""
A tuple of the physical and bound name passed to -R or -Q.
"""
IQR_INCLUDE_ARGUMENT = Tuple[IQR_PHYSICAL_PATH, None]
"""
A tuple of one element, the path passed to -I.
"""
IQR_ARGUMENT = Union[IQR_INCLUDE_ARGUMENT, IQR_BINDING_ARGUMENT]
"""
An instance that could be either arguments passed to -R, -Q, or -I.
"""

I_FLAG_REGEX = re.compile(r"-I (?P<src>\S+)")
Q_FLAG_REGEX = re.compile(r"-Q (?P<src>\S+)(\s*|\s+)(?P<tgt>\S+)")
R_FLAG_REGEX = re.compile(r"-R (?P<src>\S+)(\s*|\s+)(?P<tgt>\S+)")
R_FLAG_REGEX = re.compile(
    r"-R\s+(?P<src>\S+)(^(?!.*sqlbuddy.*).*$|,|\s+)(?P<tgt>\S+)")
IQR_REGEX = {
    'I': I_FLAG_REGEX,
    'Q': Q_FLAG_REGEX,
    'R': R_FLAG_REGEX,
}


def extract_iqr_flag_values(
    string: str,
    flag: IQR_FLAG,
) -> List[IQR_ARGUMENT]:
    """
    Extract paths and logical names using IQR arguments.

    Parameters
    ----------
    string : str
        String that could contain IQR arguments.
    flag : IQR_FLAG
        The letter in the argument -(I|Q|R).

    Returns
    -------
    Union[IQR_ARGUMENT]
        Extract tuples for value for each instance of
        flag usage. 2 values in each tuple for -R and -Q,
        while 1 value in each tuple for -I.
    """
    matches: List[IQR_ARGUMENT] = []
    for match in re.finditer(IQR_REGEX[flag], string):
        group_dict = match.groupdict()
        if 'tgt' in group_dict:
            item: IQR_BINDING_ARGUMENT = (group_dict['src'], group_dict['tgt'])
        else:
            item: IQR_INCLUDE_ARGUMENT = (group_dict.get('src'), None)
        matches.append(item)
    return matches


class IQRFlag(Enum):
    """
    Enumeration of different IQR flags.
    """

    NONE = None
    I = "I"  # noqa: E741
    Q = "Q"
    R = "R"

    @property
    def regex(self):
        """
        Return compiled regex expression to extract args.
        """
        return IQR_REGEX[self.value]

    def parse_string(self, string: str) -> List[IQR_ARGUMENT]:
        """
        Extract arguments from a string.

        Parameter
        ---------
        string: str
            A string containing one or more IQR arguments.

        Returns
        -------
        List[IQR_ARGUMENT]:
            List of tuples where the first element in the
            tuple is a physical path and the second value
            , if present, is the logical name bound to
            the physical path.  The -I argument does not
            have a second argument.
        """
        return extract_iqr_flag_values(string, self.value)


def extract_from_file(file: str) -> Dict[IQRFlag, List[IQR_ARGUMENT]]:
    """
    Extract arguments from a file.

    Parameters
    ----------
    file: str
        A path to a _CoqProject file.

    Returns
    -------
    Dict[IQRFlag, List[IQR_ARGUMENT]]:
        Each key is an IQRFlag that the corresponding
        values are list of IQR arguments using that
        flag extracted from the file.
    """
    with open(file, "r") as f:
        data = f.read()
    return {
        flag: flag.parse_string(data)
        for flag in IQRFlag
        if flag is not IQRFlag.NONE
    }


@dataclass
class ProjectExtractedIQR(ProjectFile):
    """
    A node representing the extract IQR flags from a file.

    This node is specifically the children of _CoqProject files or
    MakeFiles which will have build commands that are the IQR flags.
    """

    iqr_path: Path
    iqr_name: LogicalName
    iqr_flag: IQRFlag

    def __post_init__(self):
        """
        Initialize ProjectEntity attributes.
        """
        ProjectEntity.__init__(
            self,
            self.iqr_path,
        )

    def id_component(self) -> Tuple[str, str]:
        """
        Use root entity id with IQR argument as id.
        """
        return "iqr", f"{self.iqr_flag} {self.iqr_path} {self.iqr_name}"
