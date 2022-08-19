"""
Supplies utilities for parsing OCaml versions and constraints.
"""

import abc
import re
from abc import abstractmethod, abstractproperty
from dataclasses import dataclass
from functools import cached_property, total_ordering
from importlib import import_module
from typing import ClassVar, List, Optional, Tuple, Union

from prism.util.compare import Bottom, Top
from prism.util.parse import Parseable, ParseError
from prism.util.radpytools import cachedmethod


class VersionString(str):
    """
    Strings with a custom comparison that matches OPAM version ordering.
    """

    def __lt__(self, other: str) -> bool:
        """
        See https://opam.ocaml.org/doc/Manual.html#version-ordering.
        """
        if not isinstance(other, str):
            return super().__lt__(other)
        for a, b in zip(self, other):
            if a == b:
                continue
            if a == '~':
                return True
            elif a.isascii() and a.isalpha():
                if b == '~':
                    return False
                elif b.isascii() and b.isalpha():
                    return a < b
                else:
                    return True
            elif b == '~' or (b.isascii() and b.isalpha()):
                return False
            else:
                return a < b
        if not (len(self) > len(other) and self[len(other)] == '~'):
            return (len(self) < len(other) and not other[len(self)] == '~')
        else:
            return True


@total_ordering
class Version(Parseable, abc.ABC):
    """
    An abstract base class for OCaml package versions.
    """

    _version_chars: re.Pattern = re.compile(r"[a-zA-Z0-9\-_\+\.~]+")

    def __hash__(self) -> int:  # noqa: D105
        # cannot make abstract and also have dataclass auto-derive it
        raise NotImplementedError()

    def __lt__(self, other: 'Version') -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        # TODO: pad shorter key
        return self.key < other.key

    @abstractproperty
    def key(self) -> Tuple[Union[VersionString, int]]:
        """
        Get a key by which versions may be compared.

        Returns
        -------
        Tuple[Union[VersionString, int]]
            A key that can be compared lexicographically to determine if
            one version supercedes another.
        """
        ...

    def serialize(self) -> str:
        """
        Serialize the version to a string representation.

        The name of the `Version` subclass is prepended to the version
        for enhanced deserialization.
        """
        return ",".join(
            [self.__class__.__module__,
             self.__class__.__name__,
             str(self)])

    @classmethod
    def _chain_parse(cls,
                     input: str,
                     pos: int,
                     ignore_quotes: bool = False) -> Tuple['Version',
                                                           int]:
        if cls == Version:
            cls = OCamlVersion
        begpos = pos
        version = input
        pos = cls._consume(version, pos, '"')
        has_open_quote = pos > begpos
        version = version[pos :]
        match = cls._version_chars.search(version)
        if match is not None:
            version = version[match.start(): match.end()]
            pos_ = pos + len(version)
            pos = cls._consume(input, pos_, '"')
            has_close_quote = pos > pos_
            if not ignore_quotes and (has_open_quote != has_close_quote):
                raise ParseError(Version, input[begpos :])
            parsed = cls._exhaustive_parse(version)
            pos = cls._lstrip(input, pos)
        else:
            raise ParseError(Version, input[begpos :])
        return parsed, pos

    @classmethod
    @abstractmethod
    def _exhaustive_parse(cls, input: str) -> 'Version':
        """
        Consume the entire input when parsing the version.
        """
        ...

    @classmethod
    def deserialize(cls, version: str) -> 'Version':
        """
        Deserialize a string representation of the version.
        """
        if isinstance(version, dict):
            # HACK: workaround for limitations of `seutil.io` that cause
            # the custom serialization above to get skipped
            # Track https://github.com/pengyunie/seutil/issues/31 for
            # resolution
            from dataclasses import fields

            from seutil import io
            if 'fields' in version:
                clz = OpamVersion
            else:
                clz = OCamlVersion
            field_values = {}
            for f in fields(clz):
                if f.name in version:
                    field_values[f.name] = io.deserialize(
                        version.get(f.name),
                        f.type)
            return clz(**field_values)
        else:
            module_name, class_name, version = version.split(",")
            module = import_module(module_name)
            clz = getattr(module, class_name)
            return clz.parse(version)


@dataclass(frozen=True)
class OpamVersion(Version, Parseable):
    """
    Version specifiers according to the OCaml package manager.

    Implementation based on ``src/core/opamVersionCompare.ml`` and
    ``src/core/opamVersion.ml`` available at
    https://github.com/ocaml/opam.
    See https://opam.ocaml.org/doc/Manual.html#version-ordering for more
    information.
    """

    fields: List[Union[VersionString, str]]
    """
    Alternating sequence of non-digit/digit sequences, always starting
    with a non-digit sequence even if empty.
    """
    _version_syntax: ClassVar[re.Pattern] = re.compile(
        r"^[a-zA-Z0-9\-_\+\.~]+$")
    _sequence_syntax: ClassVar[re.Pattern] = re.compile(r"([^0-9]+)?([0-9]+)")
    _digit_re: ClassVar[re.Pattern] = re.compile(r'\d')

    def __post_init__(self):
        """
        Clean up digits by converting int to str.
        """
        # is the current field supposed to be a digit or nondigit?
        nondigit = True
        for i, f in enumerate(self.fields):
            if nondigit:
                if isinstance(f, int) or self._digit_re.search(f) is not None:
                    raise TypeError(
                        f"Malformed version; digit in expected non-digit index {i}"
                    )
                elif not isinstance(f, VersionString):
                    self.fields[i] = VersionString(f)
            elif isinstance(f, int):
                self.fields[i] = str(f)
            elif not f.isdigit():
                raise TypeError(
                    f"Malformed version; non-digit in expected digit index {i}")
            nondigit = not nondigit
        # precompute padding for comparisons
        if nondigit:
            self.fields.append(VersionString())
        else:
            self.fields.append('0')

    def __hash__(self) -> int:  # noqa: D105
        return hash(tuple(self.fields))

    def __str__(self) -> str:  # noqa: D105
        return ''.join([str(f) for f in self.fields[:-1]])

    @cached_property
    def key(self) -> Tuple[Union[VersionString, int]]:  # noqa: D102
        return tuple(
            f if isinstance(f,
                            VersionString) else int(f) for f in self.fields)

    @classmethod
    def _exhaustive_parse(cls, version: str) -> Version:  # noqa: D102
        if cls._version_syntax.match(version) is None:
            raise ParseError(cls, version)

        sequence = [f for f in cls._sequence_syntax.split(version) if f]
        fields = []
        # make sure we start with a non-digit
        nondigit = True
        if sequence[0].isdigit():
            fields.append("")
            nondigit = False
        for field in sequence:
            field = VersionString(field) if nondigit else field
            fields.append(field)
            nondigit = not nondigit
        return OpamVersion(fields)

    @cachedmethod
    @staticmethod
    def less_than(x: Union['Version', str], y: Union['Version', str]) -> bool:
        """
        Return whether one version is less than another.
        """
        if isinstance(x, str):
            x = OpamVersion.parse(x)
        if isinstance(y, str):
            y = OpamVersion.parse(y)
        return x < y


@dataclass(frozen=True)
class OCamlVersion(Version):
    """
    An OCaml compiler version.

    Version semantics are derived from
    https://github.com/ocurrent/ocaml-version.
    """

    major: str
    minor: str
    patch: Optional[str] = None
    prerelease: Optional[str] = None
    extra: Optional[str] = None
    _version_syntax: ClassVar[re.Pattern] = re.compile(
        r"^(\d+).(\d+)(\.\d+)?(([+~])(.*))?$")

    def __post_init__(self):
        """
        Clean up major, minor, and patch by converting int to str.
        """
        if isinstance(self.major, int):
            super().__setattr__('major', str(self.major))
        if isinstance(self.minor, int):
            super().__setattr__('minor', str(self.minor))
        if isinstance(self.patch, int):
            super().__setattr__('patch', str(self.patch))

    def __eq__(self, other: Version) -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        elif isinstance(other, OCamlVersion):
            return self.fast_key == other.fast_key
        else:
            return self.key == other.key

    def __lt__(self, other: Version) -> bool:  # noqa: D105
        if not isinstance(other, Version):
            return NotImplemented
        elif isinstance(other, OCamlVersion):
            return self.fast_key < other.fast_key
        else:
            return self.key < other.key

    def __str__(self) -> str:
        """
        Pretty-print the version.
        """
        patch = "" if self.patch is None else f".{self.patch}"
        prerelease = "" if self.prerelease is None else f"~{self.prerelease}"
        extra = "" if self.extra is None else f"+{self.extra}"
        return f"{self.major}.{self.minor}{patch}{prerelease}{extra}"

    @cached_property
    def fast_key(
        self
    ) -> Tuple[int,
               int,
               Union[Bottom,
                     int],
               Union[Top,
                     str],
               Union[Bottom,
                     str]]:
        """
        Get a key specialized to `OCamlVersion`s.

        See Also
        --------
        Version.key
        """
        return (
            int(self.major),
            int(self.minor),
            Bottom() if self.patch is None else int(self.patch),
            # None > Some
            Top() if self.prerelease is None else self.prerelease,
            Bottom() if self.extra is None else self.extra)

    @cached_property
    def key(self) -> Tuple[Union[VersionString, int]]:  # noqa: D102
        return OpamVersion.parse(str(self)).key

    @classmethod
    def _exhaustive_parse(cls, version: str) -> Version:  # noqa: D102
        prerelease = None
        try:
            (major,
             minor,
             patch,
             _,
             sep,
             extra) = cls._version_syntax.match(version).groups()
        except (TypeError, AttributeError):
            return OpamVersion._exhaustive_parse(version)
        if sep == "~":
            if extra is None:
                prerelease = ""
            else:
                try:
                    prerelease, extra = extra.split("+", maxsplit=1)
                except ValueError:
                    prerelease = extra
                    extra = None
        elif sep == "+" and extra is None:
            extra = ""
        if patch is not None:
            patch = patch[1 :]
        return OCamlVersion(major, minor, patch, prerelease, extra)
