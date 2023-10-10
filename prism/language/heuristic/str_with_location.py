#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Module providing a class that ties strings to original file locations.
"""
import math
import re
import warnings
from dataclasses import dataclass
from functools import cached_property
from itertools import repeat
from typing import (
    Callable,
    ClassVar,
    Iterable,
    List,
    Optional,
    SupportsIndex,
    Tuple,
    Union,
)

from prism.language.gallina.analyze import SexpInfo
from prism.util.radpytools import PathLike
from prism.util.radpytools.dataclasses import default_field
from prism.util.string import escape_backslash


@dataclass(frozen=True, init=False)
class StrWithLocation(str):
    """
    Class that ties strings to their original in-file locations.

    Strings stored in objects of this class should only be those
    that have been loaded from files. The location data is only
    meaningful in that context.

    If a string spans multiple lines, it is assumed that the newline
    and other whitespace characters that situate the lines are
    present in the string.
    """

    indices: List[Tuple[int, int]] = default_field(list())
    """
    Indices that refer to the string's original location in the full
    document string. Each index in the outer list corresponds to the
    same index in the string. Each tuple in the indices list represents
    an open interval (start, end) indicating the index or indices in the
    original document the correponsding string components come from.

    If a tuple in this list does not take the form (i, i+1), it is
    likely because a substitution has been made such that the string-to-
    indices correspondence is no longer exact. A tuple of (3, 8) for
    instance might arise from replacing a substring of length 5 with a
    single character.
    """
    _bol_matcher: ClassVar[re.Pattern] = re.compile(
        r"(?:^|\n)([^\n])[^\n]*\n*$")
    """
    Pattern to match the character immediately following the last
    newline as long as newline has non-newline characters after it.
    """

    def __new__(
            cls,
            string: str = "",
            indices: Optional[List[Tuple[int,
                                         int]]] = None,
            *args,
            **kwargs) -> 'StrWithLocation':
        """
        Construct a new instance of `StrWithLocation`.

        Parameters
        ----------
        string : str, optional
            The string to be located, by default the empty string
        indices : Optional[List[Tuple[int, int]]], optional
            The indices locating the string within its original
            document, by default None, in which case the location is
            understood to be unbounded.

        Returns
        -------
        StrWithLocation
            The newly-constructed `StrWithLocation` object
        """
        if indices is None:
            indices = []
        result = super().__new__(cls, string, *args, **kwargs)
        object.__setattr__(result, 'indices', indices)
        return result

    def __init__(self, *args_ignore, **kwargs_ignore):
        """
        Provide dummy __init__.

        The __init__ function will inevitably be called, since __new__
        returns an instance of the object, but we don't actually need it
        to do anything.
        """
        self.__post_init__()

    def __post_init__(self):
        """
        Verify inputs.

        Raises
        ------
        ValueError
            If the length of the string list does not match the
            length of the loc list
        """
        if len(self) != len(self.indices):
            raise ValueError("Each character should have a location.")
        for ind in self.indices:
            if not isinstance(ind, tuple):
                raise TypeError(
                    "'indices' attribute contains object that is not a tuple. "
                    f"The incorrect type is {type(ind)}.")
            if len(ind) != 2 or ind[0] > ind[1]:
                raise ValueError(
                    f"Expected two locations in ascending order, got {ind}")

    def __add__(self, other: str) -> 'StrWithLocation':
        """
        Combine this instance with another using '+'.
        """
        if isinstance(other, StrWithLocation):
            return StrWithLocation(
                str(self) + str(other),
                self.indices + other.indices)
        else:
            return NotImplemented

    def __eq__(self, other: object) -> bool:
        """
        Test equality of objects.
        """
        if isinstance(other, str) and not hasattr(other, 'indices'):
            # i.e., other is an actual str
            return str(self) == other
        elif isinstance(other, StrWithLocation):
            return str(self) == str(other) and self.indices == other.indices
        else:
            return NotImplemented

    def __getitem__(
            self,
            idx: Union[SupportsIndex,
                       slice]) -> 'StrWithLocation':
        """
        Return a portion of the located string at the given idx.
        """
        new_indices = self.indices.__getitem__(idx)
        if isinstance(new_indices, tuple):
            new_indices = [new_indices]
        return StrWithLocation(super().__getitem__(idx), new_indices)

    @cached_property
    def start(self) -> Optional[int]:
        """
        Get the least first index in the indices list.
        """
        return min([x for x, _ in self.indices]) if self.indices else None

    @cached_property
    def end(self) -> Optional[int]:
        """
        Get the largest second index in the indices list.
        """
        return max([x for _, x in self.indices]) if self.indices else None

    def get_location(
            self,
            file_contents: str,
            filename: PathLike,
            start_idx: int = 0,
            newlines_so_far: int = 0) -> SexpInfo.Loc:
        """
        Derive the SexpInfo.Loc location from the located string.

        The final two arguments are intended to be used when a large
        batch of locations are sequentially computed in order to reduce
        the search space for newlines and for BoL matches.

        The correct location can be derived with only the first two
        arguments, but providing the final two should yield a speed-up.

        Parameters
        ----------
        file_contents : str
            The full file contents in string form
        filename : PathLike
            The filename the file contents were loaded from
        start_idx : int, optional
            Index of file_contents to start with. Pass this argument if
            some of the document has already been processed up to this
            index. If any newlines have been encountered so far, an
            accurate count should be given to `newlines_so_far` for that
            computation to be correct. By default 0.
        newlines_so_far : int, optional
            The number of newlines encountered in the document in any
            prior sequential processing. By default 0.

        Returns
        -------
        SexpInfo.Loc
            The derived SexpInfo.Loc location
        """
        if not isinstance(filename, str):
            filename = str(filename)
        start = self.start
        if start is None:
            start = 0
        end = self.end
        if end is None:
            end = len(file_contents)
        assert start_idx <= start
        num_newlines_before_string = file_contents.count(
            "\n",
            start_idx,
            start) + newlines_so_far
        num_newlines_in_string = file_contents.count("\n", self.start, self.end)
        bol_match = self._bol_matcher.search(
            file_contents,
            pos=0,
            endpos=start + 1)
        assert bol_match is not None
        bol_pos = bol_match.start(1)
        bol_last_match = self._bol_matcher.search(
            file_contents,
            pos=0,
            endpos=end)
        assert bol_last_match is not None
        bol_pos_last = bol_last_match.start(1)
        return SexpInfo.Loc(
            filename=filename,
            lineno=num_newlines_before_string,
            bol_pos=bol_pos,
            lineno_last=num_newlines_before_string + num_newlines_in_string,
            bol_pos_last=bol_pos_last,
            beg_charno=start,
            end_charno=end - 1)

    def join(self, it: Iterable[str]) -> 'StrWithLocation':
        """
        Reimplement str join method for StrWithLocation.

        Parameters
        ----------
        it : Iterable[StrWithLocation]
            Iterable of StrWithLocation objects to be joined

        Returns
        -------
        StrWithLocation
            Joined StrWithLocation object
        """
        # make a copy of input in case it can only be iterated once
        it = list(it)
        str_part = super().join(it)
        indices_part = []
        for i, item in enumerate(it):
            if not isinstance(item, StrWithLocation):
                raise NotImplementedError(
                    f"Joining with type {type(item)} not implemented.")
            if i < len(it) - 1:
                indices_part.extend(item.indices)
                indices_part.extend(self.indices)
            else:
                indices_part.extend(item.indices)
        return StrWithLocation(str_part, indices_part)

    def lstrip(self, s: Optional[str] = None) -> 'StrWithLocation':
        """
        Mimic str lstrip method, keeping track of location.
        """
        if s is not None:
            raise NotImplementedError(
                "Stripping of given strings not implemented.")
        stripped = super().lstrip()
        len_to_strip = len(self) - len(stripped)
        return StrWithLocation(stripped, self.indices[len_to_strip :])

    def rstrip(self, s: Optional[str] = None) -> 'StrWithLocation':
        """
        Mimic str rstrip method, keeping track of location.
        """
        if s is not None:
            raise NotImplementedError(
                "Stripping of given strings not implemented.")
        stripped = super().rstrip()
        len_to_strip = len(self) - len(stripped)
        end_idx = -1 * len_to_strip if len_to_strip > 0 else None
        return StrWithLocation(stripped, self.indices[: end_idx])

    def strip(self, s: Optional[str] = None) -> 'StrWithLocation':
        """
        Mimic str strip method, but don't take an argument.
        """
        return self.lstrip(s).rstrip(s)

    @classmethod
    def create_from_file_contents(cls, file_contents: str) -> 'StrWithLocation':
        """
        Create an instance of StrWithLocation from doc contents str.

        Parameters
        ----------
        file_contents : str
            A single string containing a the unaltered, full
            contents of a Coq file

        Returns
        -------
        StrWithLocation
            The instance created from the file contents
        """
        return cls(
            file_contents,
            [(i,
              i + 1) for i in range(len(file_contents))])

    @classmethod
    def re_split(
            cls,
            pattern: Union[str,
                           re.Pattern],
            string: 'StrWithLocation',
            maxsplit: int = 0,
            flags: Union[int,
                         re.RegexFlag] = 0) -> List['StrWithLocation']:
        """
        Mimic re.split, but maintain location information.

        Parameters
        ----------
        pattern : Union[str, re.Pattern[str]]
            Pattern to match for split
        string : StrWithLocation
            The string with location to split
        maxsplit : int, optional
            Maximum number of splits to do; unlimited if 0, by
            default 0
        flags : int or re.RegexFlag, optional
            Flags to pass to compile operation if pattern is a str,
            by default 0

        Returns
        -------
        List[StrWithLocation]
            A list of strings with locations after being split by
            the pattern
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern, flags)
        located_result: List[StrWithLocation] = []
        string = cls(str(string), string.indices)
        split_list = pattern.split(string, maxsplit=maxsplit)
        match_start_pos = 0
        for split in split_list:
            match_start = string.index(split, match_start_pos)
            match_end = match_start + len(split)
            located_result.append(
                cls(split,
                    string.indices[match_start : match_end]))
            match_start_pos = match_end
        return located_result

    @classmethod
    def re_sub(
            cls,
            pattern: Union[str,
                           re.Pattern],
            repl: Union[str,
                        Callable[[re.Match],
                                 str]],
            string: 'StrWithLocation',
            count: int = 0,
            flags: Union[int,
                         re.RegexFlag] = 0) -> 'StrWithLocation':
        """
        Mimic re.sub, but maintain location information.

        This method does not currently support completely removing
        portions of the string while remembering the location of the
        removed copmonent. In other words, if the repl string is "", the
        location information of any matches will be completely lost.

        Parameters
        ----------
        pattern : Union[str, re.Pattern]
            Pattern to match for split
        repl : Union[str, Callable[[re.Match], str]]]
            String to substitute in when pattern is found or a function
            with which to compute a substitution given a match.
        string : StrWithLocation
            The string to perform the substitution on
        count : int, optional
            Maximum number of substitutions to do; unlimited if 0,
            by default 0
        flags : int or re.RegexFlag, optional
            Flags to pass to compile operation if pattern is a str,
            by default 0

        Returns
        -------
        StrWithLocation
            Located string with substitution performed
        """
        if repl == "":
            warnings.warn(
                "Substituting in an empty string will cause location "
                "information where the empty string is substituted to"
                " be lost.")
        string = cls(str(string), string.indices)
        if isinstance(pattern, str):
            pattern = re.compile(pattern, flags)
        match = pattern.search(string)
        if not match:
            return string
        repls: Iterable[str]
        if callable(repl):
            repls = []

            def _repl(match: re.Match, repl=repl) -> str:
                nonlocal repls
                sub = repl(match)
                repls.append(sub)  # type: ignore
                return sub

            repl = _repl
        else:
            repls = repeat(repl)
            repl = escape_backslash(repl)

        subbed_string = pattern.sub(repl, string, count)
        subbed_indices = []
        prev_end = 0
        idx = 0
        for match, repl in zip(pattern.finditer(string), repls):
            if count > 0 and idx >= count:
                break
            else:
                # Get the indices prior to subbed location
                subbed_indices.extend(string.indices[prev_end : match.start()])
                # Get the indices for the next subbed location
                subbed = string[match.start(): match.end()]
                start = subbed.start
                end = subbed.end
                assert start is not None
                assert end is not None
                step = (end - start) / len(repl)
                subbed_indices.extend(
                    [
                        (
                            start + math.floor(i * step),
                            min(end,
                                start + math.ceil((i + 1) * step)))
                        for i in range(len(repl))
                    ])
                prev_end = match.end()
                idx += 1
        subbed_indices.extend(string.indices[prev_end :])
        return cls(subbed_string, subbed_indices)
