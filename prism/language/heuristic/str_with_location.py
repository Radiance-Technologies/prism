"""
Module providing a class that ties strings to original file locations.
"""
import re
from dataclasses import dataclass
from functools import cached_property
from typing import ClassVar, Iterable, List, Optional, Tuple, Union

from typing_extensions import LiteralString

from prism.language.gallina.analyze import SexpInfo
from prism.util.radpytools.dataclasses import default_field


@dataclass(frozen=True)
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
    _bol_matcher: ClassVar[re.Pattern] = re.compile(r"(?<=\n)[^\n]+$")
    _bol_last_matcher: ClassVar[re.Pattern] = re.compile(
        r"(?<=\n)[^\S\n]+(?=\S[^\n]*$)")

    def __new__(
            cls,
            string: LiteralString,
            indices: List[Tuple[int,
                                int]],
            *args,
            **kwargs) -> 'StrWithLocation':
        """
        Construct a new instance of `StrWithLocation`.

        Parameters
        ----------
        string : LiteralString
            The string to be located
        indices : List[Tuple[int, int]]
            The indices locating the string within its original document

        Returns
        -------
        StrWithLocation
            The newly-constructed `StrWithLocation` object
        """
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
            raise ValueError("Each string should have a location.")
        for ind in self.indices:
            if not isinstance(ind, tuple):
                raise TypeError(
                    "indices attribute contains object that is not tuple. The"
                    f" incorrect type is {type(ind)}.")

    def __add__(self, other: 'StrWithLocation'):
        """
        Combine this instance with another using '+'.
        """
        if isinstance(other, StrWithLocation):
            return StrWithLocation(
                str(self) + str(other),
                self.indices + other.indices)
        else:
            return NotImplemented

    def __eq__(self, other: Union[str, 'StrWithLocation']) -> bool:
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

    def __getitem__(self, idx: Union[int, slice]) -> 'StrWithLocation':
        """
        Return a portion of the located string at the given idx.
        """
        return StrWithLocation(super().__getitem__(idx), self.indices[idx])

    @cached_property
    def start(self) -> Optional[int]:
        """
        Get the first index in the indices list.

        With respect to the start and end properties, `string`
        corresponds to <original document string>[start, end].
        """
        return self.indices[0][0] if self.indices else None

    @cached_property
    def end(self) -> Optional[int]:
        """
        Get the final index in the indices list.

        With respect to the start and end properties, `string`
        corresponds to <original document string>[start, end].
        """
        return self.indices[-1][1] if self.indices else None

    def get_location(self, file_contents: str, filename: str) -> SexpInfo.Loc:
        """
        Derive the SexpInfo.Loc location from the located string.

        Parameters
        ----------
        file_contents : str
            The full file contents in string form
        filename : str
            The filename the file contents were loaded from

        Returns
        -------
        SexpInfo.Loc
            The derived SexpInfo.Loc location
        """
        num_newlines_before_string = file_contents[: self.start].count("\n")
        num_newlines_in_string = file_contents[self.start : self.end].count(
            "\n")
        bol_match = self._bol_matcher.search(file_contents[: self.start])
        bol_pos = len(bol_match[0]) if bol_match is not None else 0
        bol_last_match = self._bol_last_matcher.search(
            file_contents[: self.end])
        bol_pos_last = len(
            bol_last_match[0]) if bol_last_match is not None else 0
        return SexpInfo.Loc(
            filename=filename,
            lineno=num_newlines_before_string,
            bol_pos=bol_pos,
            lineno_last=num_newlines_before_string + num_newlines_in_string,
            bol_pos_last=bol_pos_last,
            beg_charno=self.start,
            end_charno=self.end - 1)

    def join(self, it: Iterable['StrWithLocation']) -> 'StrWithLocation':
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
        str_part = super().join(it)
        indices_part = []
        for i, item in enumerate(it):
            if i < len(it) - 1:
                indices_part.extend(item.indices)
                indices_part.extend(self.indices)
            else:
                indices_part.extend(item.indices)
        return StrWithLocation(str_part, indices_part)

    def lstrip(self) -> 'StrWithLocation':
        """
        Mimic str lstrip method, keeping track of location.
        """
        stripped = super().lstrip()
        len_to_strip = len(self) - len(stripped)
        return StrWithLocation(stripped, self.indices[len_to_strip :])

    def restore_final_ellipsis(self) -> 'StrWithLocation':
        """
        Restore ellipsis at the end of a line.

        Only call this method if there were originally an ellipsis at
        the end of this string. Otherwise, the indices will be garbage.
        """
        result_str = str(self) + "..."
        result_indices = self.indices
        result_indices.extend(
            [(self.end + i,
              self.end + i + 1) for i in range(3)])
        return StrWithLocation(result_str, result_indices)

    def restore_final_period(self) -> 'StrWithLocation':
        """
        Restore the final period at the end of a sentence.

        Only call this method if there was originally a period at the
        end of this string. Otherwise, the indices will be garbage.
        """
        if not self.endswith("."):
            result_str = str(self)
            result_indices = self.indices
            result_str += "."
            result_indices.append((self.end, self.end + 1))
            return StrWithLocation(result_str, result_indices)
        else:
            return self

    def rstrip(self) -> 'StrWithLocation':
        """
        Mimic str rstrip method, keeping track of location.
        """
        stripped = super().rstrip()
        len_to_strip = len(self) - len(stripped)
        end_idx = -1 * len_to_strip if len_to_strip > 0 else None
        return StrWithLocation(stripped, self.indices[: end_idx])

    def strip(self) -> 'StrWithLocation':
        """
        Mimic str strip method, but don't take an argument.
        """
        return self.lstrip().rstrip()

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
    def empty(cls) -> 'StrWithLocation':
        """
        Create and return an empty instance.
        """
        return cls("", [])

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
            repl: str,
            string: 'StrWithLocation',
            count: int = 0,
            flags: Union[int,
                         re.RegexFlag] = 0) -> 'StrWithLocation':
        """
        Mimic re.sub, but maintain location information.

        This method has no way to account for the location of
        portions that are completely removed. That is, if the repl
        string is "", the location information of any matches will
        be completely lost.

        Parameters
        ----------
        pattern : Union[str, re.Pattern]
            Pattern to match for split
        repl : str
            String to substitute in when pattern is found
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
        string = cls(str(string), string.indices)
        if isinstance(pattern, str):
            pattern = re.compile(pattern, flags)
        match = pattern.search(string)
        if not match:
            return string
        subbed_string = pattern.sub(repl, string, count)
        subbed_indices = []
        prev_end = 0
        idx = 0
        for match in pattern.finditer(string):
            if count > 0 and idx >= count:
                break
            else:
                # Get the indices prior to subbed location
                subbed_indices.extend(string.indices[prev_end : match.start()])
                # Get the indices for the next subbed location
                subbed_indices.extend(
                    [(match.start(),
                      match.end()) for _ in range(len(repl))])
                prev_end = match.end()
                idx += 1
        subbed_indices.extend(string.indices[prev_end :])
        return cls(subbed_string, subbed_indices)
