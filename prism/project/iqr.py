"""
Provides an abstraction of Coq library linking command-line options.
"""

import argparse
import os
import pathlib
from dataclasses import dataclass
from typing import List, Set, Tuple

from prism.util.path import get_relative_path


@dataclass
class IQR:
    """
    Dataclass for storing IQR arguments.

    See https://coq.inria.fr/refman/practical-tools/coq-commands.html
    for more information.
    """

    I: Set[str]  # noqa: E741
    Q: Set[Tuple[str, str]]  # set of pairs of str
    R: Set[Tuple[str, str]]  # set of pairs of str
    pwd: os.PathLike = ""
    """
    The working directory to which all of the options are assumed to be
    relative.
    """
    delim: str = ","
    """
    The delimiter used between relative and logical paths, by default a
    comma for compatibility with SerAPI.
    A space should be used for compatibility with Coq.
    """

    def __or__(self, other: 'IQR') -> 'IQR':  # noqa: D105
        if not isinstance(other, IQR):
            return NotImplemented
        self_pwd = pathlib.Path(self.pwd).resolve()
        other_pwd = pathlib.Path(other.pwd).resolve()
        if self_pwd != other_pwd:
            pwd = os.path.commonpath([self_pwd, other_pwd])
            return self.relocate(pwd) | other.relocate(pwd)
        else:
            return IQR(
                self.I | other.I,
                self.Q | other.Q,
                self.R | other.R,
                self.pwd,
                self.delim)

    def __str__(self) -> str:
        """
        Get the options as they would appear on the command line.
        """
        options = [f"-I {i}" for i in self.I]
        options.extend([f"-Q {p}{self.delim}{q}" for p, q in self.Q])
        options.extend([f"-R {p}{self.delim}{r}" for p, r in self.R])
        return " ".join(options)

    def union(self, other: 'IQR') -> 'IQR':
        """
        Compute the union of two IQR configurations.

        If the configurations do not share the same working directory,
        then the working directory of their union will be the longest
        common path shared between their working directories.
        """
        return self | other

    def relocate(self, pwd: os.PathLike) -> 'IQR':
        """
        Reinterpret the IQR arguments relative to another path.

        Parameters
        ----------
        pwd : os.PathLike, optional
            The path relative to which the IQR options should be
            reinterpreted, by default "".

        Returns
        -------
        str
            The reinterpreted arguments.
        """
        prefix = get_relative_path(self.pwd, pwd)
        return IQR(
            {str(prefix / i) for i in self.I},
            {(str(prefix / p),
              q) for p,
             q in self.Q},
            {(str(prefix / p),
              r) for p,
             r in self.R},
            pwd,
            self.delim)

    @classmethod
    def extract_iqr(cls, args: List[str], pwd: os.PathLike = "") -> 'IQR':
        """
        Extract IQR args from command args; return as IQR dataclass.

        Parameters
        ----------
        args : List[str]
            A list of string arguments associated with a command.
        pwd : os.PathLike, optional
            The directory in which the command was executed, by default
            an empty string.

        Returns
        -------
        IQR
            Args processed into IQR dataclass
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-I',
            metavar=('dir'),
            nargs=1,
            action='append',
            default=[],
            help='append filesystem to ML load path')

        parser.add_argument(
            '-Q',
            metavar=('dir',
                     'coqdir'),
            nargs=2,
            action='append',
            default=[],
            help='append filesystem dir mapped to coqdir to coq load path')

        parser.add_argument(
            '-R',
            metavar=('dir',
                     'coqdir'),
            nargs=2,
            action='append',
            default=[],
            help='recursively append filesystem dir mapped '
            'to coqdir to coq load path')
        args, _ = parser.parse_known_args(args)

        return cls(
            I=set(args.I),
            Q={tuple(i) for i in args.Q},
            R={tuple(i) for i in args.R},
            pwd=pwd)
