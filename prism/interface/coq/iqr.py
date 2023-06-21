"""
Provides an abstraction of Coq library linking command-line options.
"""
import argparse
import os
import pathlib
import re
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Iterator, List, Optional, Set, Tuple, Union

from prism.interface.coq.re_patterns import (
    IDENT_PATTERN,
    QUALIFIED_IDENT_PATTERN,
)
from prism.util.path import get_relative_path
from prism.util.radpytools import PathLike


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
    pwd: PathLike = ""
    """
    The working directory to which all of the options are assumed to be
    relative.
    """
    _i_regex: ClassVar[re.Pattern] = re.compile(r"-I\s+(?P<phy>\S+)")
    _q_regex: ClassVar[re.Pattern] = re.compile(
        r"-Q\s+(?P<phy>\S+)(?:\s+|,)(?!-I|-Q|-R)(?P<log>[^,\s]+)")
    _r_regex: ClassVar[re.Pattern] = re.compile(
        r"-R\s+(?P<phy>\S+)(?:\s+|,)(?!-I|-Q|-R)(?P<log>[^,\s]+)")

    def __or__(self, other: 'IQR') -> 'IQR':  # noqa: D105
        if not isinstance(other, IQR):
            return NotImplemented
        self_pwd = Path(self.pwd).resolve()
        other_pwd = Path(other.pwd).resolve()
        if self_pwd != other_pwd:
            pwd = os.path.commonpath([self_pwd, other_pwd])
            return self.relocate(pwd) | other.relocate(pwd)
        else:
            return IQR(
                self.I | other.I,
                self.Q | other.Q,
                self.R | other.R,
                self.pwd)

    def __str__(self) -> str:
        """
        Get the options as they would appear on the command line.
        """
        return self.as_coq_args()

    def _QR_bindings_iter(
            self,
            QR: Set[Tuple[str,
                          str]],
            root: Optional[PathLike] = None) -> Iterator[Tuple[Path,
                                                               str]]:
        """
        Get an iterator over bound physical and logical library paths.

        Parameters
        ----------
        QR : Set[Tuple[str, str]]
            Either `Q` or `R` bindings.
        root : Optional[PathLike], optional
            The root from which to evaluate IQR flags, by default `pwd`.

        Yields
        ------
        Tuple[Path, str]
            A pair comprising a physical path bound to a fully qualified
            logical library name.
        """
        # https://coq.inria.fr/refman/language/core/modules.html#libraries-and-filesystem
        # https://coq.inria.fr/refman/proof-engine/vernacular-commands.html#compiled-files
        if root is None:
            root = self.pwd
        root = Path(root)
        for path, prefix in QR:
            bound_path = root / path
            for subdir, _, filenames in os.walk(bound_path):
                subpath = get_relative_path(subdir, bound_path)
                if all(IDENT_PATTERN.match(part) for part in subpath.parts):
                    suffix = '.'.join(subpath.parts)
                    if suffix:
                        lib = '.'.join([prefix, suffix])
                    else:
                        lib = prefix
                    yield subpath, lib
                    # catch actual Coq files/libraries
                    for filename in filenames:
                        filepath = subpath / filename
                        libname = filepath.stem
                        if (filepath.suffix == '.v'
                                and QUALIFIED_IDENT_PATTERN.match(libname)):
                            yield filepath, '.'.join([lib, libname])

    def as_coq_args(self) -> str:
        """
        Get the options as they would be given to the Coq compiler.
        """
        options = [f"-I {i}" for i in self.I]
        options.extend([f"-Q {p} {q}" for p, q in self.Q])
        options.extend([f"-R {p} {r}" for p, r in self.R])
        return " ".join(options)

    def as_serapi_args(self) -> str:
        """
        Get the options as they would be given to SerAPI executables.
        """
        options = [f"-I {i}" for i in self.I]
        options.extend([f"-Q {p},{q}" for p, q in self.Q])
        options.extend([f"-R {p},{r}" for p, r in self.R])
        return " ".join(options)

    def bindings_iter(
            self,
            root: Optional[PathLike] = None) -> Iterator[Tuple[Path,
                                                               str]]:
        """
        Get an iterator over bound physical and logical library paths.

        Parameters
        ----------
        root : Optional[PathLike], optional
            The root from which to evaluate IQR flags, by default `pwd`.

        Yields
        ------
        Tuple[Path, str]
            A pair comprising a physical path bound to a fully qualified
            logical library name.
        """
        yield from self.Q_bindings_iter(root)
        yield from self.R_bindings_iter(root)

    def local_libraries(self, root: Optional[PathLike] = None) -> List[str]:
        """
        Get a list of all locally bound libraries.
        """
        return [lib for _, lib in self.bindings_iter(root)]

    def Q_bindings_iter(
            self,
            root: Optional[PathLike] = None) -> Iterator[Tuple[Path,
                                                               str]]:
        """
        Get an iterator over Q-bound physical and logical library paths.

        Parameters
        ----------
        root : Optional[PathLike], optional
            The root from which to evaluate IQR flags, by default `pwd`.

        Yields
        ------
        Tuple[Path, str]
            A pair comprising a physical path bound to a fully qualified
            logical library name.
        """
        return self._QR_bindings_iter(self.Q, root)

    def R_bindings_iter(
            self,
            root: Optional[PathLike] = None) -> Iterator[Tuple[Path,
                                                               str]]:
        """
        Get an iterator over R-bound physical and logical library paths.

        Parameters
        ----------
        root : Optional[PathLike], optional
            The root from which to evaluate IQR flags, by default `pwd`.

        Yields
        ------
        Tuple[Path, str]
            A pair comprising a physical path bound to a fully qualified
            logical library name.
        """
        return self._QR_bindings_iter(self.R, root)

    def union(self, other: 'IQR') -> 'IQR':
        """
        Compute the union of two IQR configurations.

        If the configurations do not share the same working directory,
        then the working directory of their union will be the longest
        common path shared between their working directories.
        """
        return self | other

    def relocate(self, pwd: PathLike) -> 'IQR':
        """
        Reinterpret the IQR arguments relative to another path.

        Parameters
        ----------
        pwd : PathLike, optional
            The path relative to which the IQR options should be
            reinterpreted, by default "".

        Returns
        -------
        IQR
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
            pwd)

    @classmethod
    def parse_args(
            cls,
            args: Union[str,
                        List[str]],
            pwd: PathLike = "") -> 'IQR':
        """
        Extract IQR args from command args; return as IQR dataclass.

        Parameters
        ----------
        args : Union[str, List[str]]
            A list of string arguments associated with a command or an
            unsplit string of arguments (e.g., options for SerAPI
            commands)
        pwd : PathLike, optional
            The directory in which the command was executed, by default
            an empty string.

        Returns
        -------
        IQR
            Args processed into IQR dataclass
        """
        if isinstance(args, list):
            # use optimized argparser if already a list
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
            parsed_args, _ = parser.parse_known_args(args)
            I_ = {i[0] for i in parsed_args.I}
            Q = typing.cast(
                Set[Tuple[str,
                          str]],
                {tuple(i) for i in parsed_args.Q})
            R = typing.cast(
                Set[Tuple[str,
                          str]],
                {tuple(i) for i in parsed_args.R})
        else:
            # these could be serapi options with embedded commas
            I_ = {m.group('phy') for m in cls._i_regex.finditer(args)}
            Q = {
                (m.group('phy'),
                 m.group('log')) for m in cls._q_regex.finditer(args)
            }
            R = {
                (m.group('phy'),
                 m.group('log')) for m in cls._r_regex.finditer(args)
            }
        return cls(I_, Q, R, pwd=pwd)

    def get_local_modpath(self, filename: PathLike) -> str:
        """
        Infer the module path for the given file.

        Parameters
        ----------
        filename : PathLike
            The physical path to a project file relative to the project
            root.
        iqr : IQR
            Arguments with which to initialize `sertop`, namely IQR
            flags.

        Returns
        -------
        modpath : str
            The logical library path one would use if the indicated file
            was imported or required in another.
        """
        # strip file extension, if any
        if not isinstance(filename, pathlib.Path):
            filename = pathlib.Path(filename)
        filename = str(filename.with_suffix(''))
        # identify the correct logical library prefix for this filename
        matched = False
        dot_log = None
        for (phys, log) in (self.Q | self.R):
            if filename.startswith(phys):
                filename = filename[len(phys):]
            else:
                if phys == ".":
                    dot_log = log
                continue
            # ensure that the filename gets separated from the logical
            # prefix by a path separator (to be replaced with a period)
            if filename[0] != os.path.sep:
                sep = os.path.sep
            else:
                sep = ''
            filename = sep.join([log, filename])
            matched = True
            break
        if not matched and dot_log is not None:
            # ensure that the filename gets separated from the logical
            # prefix by a path separator (to be replaced with a period)
            if filename[0] != os.path.sep:
                sep = os.path.sep
            else:
                sep = ''
            filename = sep.join([dot_log, filename])
        # else we implicitly map the working directory to an empty
        # logical prefix
        # convert rest of physical path to logical
        path = filename.split(os.path.sep)
        if path == ['']:
            path = []
        modpath = ".".join([dirname.capitalize() for dirname in path])
        return modpath
