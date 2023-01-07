"""
Utilities for representing and parsing Git diffs.
"""

import os
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import ClassVar, List, Optional, Union

from prism.util.radpytools.dataclasses import default_field
from prism.util.re import regex_from_options


@dataclass
class Change:
    """
    A discrete change in a contiguous range of lines of a file.
    """

    before_filename: Optional[Path] = None
    """
    The filename before the change.

    If None, then the file was created in the change.
    """
    after_filename: Optional[Path] = None
    """
    The filename after the change.

    If None, then the file was deleted in the change.
    """
    before_range: range = range(0, 0)
    """
    The range of lines changed in the original file.
    """
    after_range: range = range(0, 0)
    """
    The range of lines encompassing the change in the altered file.
    """
    removed_lines: List[str] = default_field([])
    """
    The text of lines in the original file that were removed or altered.
    """
    added_lines: List[str] = default_field([])
    """
    The text of lines in the altered file that were added or altered.
    """

    def __post_init__(self) -> None:
        """
        Ensure consistent typing.
        """
        if isinstance(self.before_filename, str):
            self.before_filename = Path(self.before_filename)
        if isinstance(self.after_filename, str):
            self.after_filename = Path(self.after_filename)

    def __str__(self) -> str:
        """
        Format the change in the style of a Git diff.
        """
        if self.is_pure_rename:
            lines = [
                f"rename from {self.before_filename}",
                f"rename to {self.after_filename}"
            ]
        else:
            before_name = self.before_filename
            before_name = "/dev/null" if before_name is None else f"a/{before_name}"
            after_name = self.after_filename
            after_name = "/dev/null" if after_name is None else f"b/{after_name}"
            before_count = len(self.before_range)
            before_count = "" if before_count == 1 else f",{before_count}"
            after_count = len(self.after_range)
            after_count = "" if after_count == 1 else f",{after_count}"
            lines = [
                f"--- {before_name}",
                f"+++ {after_name}",
                f"@@ -{self.before_range.start}{before_count}"
                f" +{self.after_range.start}{after_count} @@"
            ]
            lines.extend(f"-{line}" for line in self.removed_lines)
            lines.extend(f"+{line}" for line in self.added_lines)
        return '\n'.join(lines)

    @property
    def is_rename(self) -> bool:
        """
        Return whether this change includes a file rename.
        """
        return (
            self.before_filename is not None and self.after_filename is not None
            and self.before_filename != self.after_filename)

    @property
    def is_pure_rename(self) -> bool:
        """
        Return whether this change represents just a rename.
        """
        return (
            self.before_filename is not None and self.after_filename is not None
            and not self.before_range and not self.after_range
            and not self.removed_lines and not self.added_lines)


@dataclass
class GitDiff:
    """
    A diff between two commits.

    Notes
    -----
    Some Git diff options that alter the format of the resulting diff
    may not be supported or lead to unexpected behavior.
    In particular, word diffs (``--word-diff``) are not currently
    supported.

    In addition, it is recommended that one use the ``-U0`` option to
    limit the context of changes to zero lines so that the line ranges
    extracted in the `changes` method correspond only to changed line
    ranges and not unchanged context.
    """

    filename_regex: ClassVar[re.Pattern] = re.compile(
        "(?:^|(?<=\n))"
        r"---\s+(?P<before_filename>\S+)\s+"
        r"\+\+\+\s+(?P<after_filename>\S+)")
    rename_regex: ClassVar[re.Pattern] = re.compile(
        "(?:^|(?<=\n))"
        r"rename\s+from\s+(?P<before_rename>\S+)\s+"
        r"rename\s+to\s+(?P<after_rename>\S+)")
    location_regex: ClassVar[re.Pattern] = re.compile(
        "(?:^|(?<=\n))"
        r"@@\s*-(?P<before_start>\d+)(?:,(?P<before_count>\d+))?"
        r"\s*\+(?P<after_start>\d+)(?:,(?P<after_count>\d+))?\s*@@")
    removed_line_regex: ClassVar[re.Pattern] = re.compile(
        "(?:^|(?<=\n))"
        r"-(?P<removed_line>.*)(?:"
        "\n|$)")
    added_line_regex: ClassVar[re.Pattern] = re.compile(
        "(?:^|(?<=\n))"
        r"\+(?P<added_line>.*)(?:"
        "\n|$)")
    change_regex: ClassVar[re.Pattern] = regex_from_options(
        [
            filename_regex.pattern,
            rename_regex.pattern,
            location_regex.pattern,
            removed_line_regex.pattern,
            added_line_regex.pattern
        ],
        False,
        False)

    text: str
    """
    The raw text of the diff as returned by ``git diff``.
    """

    @cached_property
    def changes(self) -> List[Change]:
        """
        Get the list of changes that comprise the diff.
        """
        return self.parse_changes(self.text)

    @classmethod
    def parse_changes(cls, text: str) -> List[Change]:
        """
        Parse a list of discrete changes from the text of a Git diff.

        Parameters
        ----------
        text : str
            The raw text of a Git diff.

        Returns
        -------
        List[Change]
            The list of changes contained in the diff.
        """
        changes: List[Change] = []
        context = Change()

        for match in cls.change_regex.finditer(text):
            if match["before_filename"] is not None:
                assert match["after_filename"] is not None
                context.before_filename = cls.mkpath(match["before_filename"])
                context.after_filename = cls.mkpath(match["after_filename"])
            elif match["before_rename"] is not None:
                assert match["after_rename"] is not None
                changes.append(
                    Change(
                        Path(match["before_rename"]),
                        Path(match["after_rename"])))
            elif match["before_start"] is not None:
                assert match["after_start"] is not None
                context.before_range = cls.mkrange(
                    match["before_start"],
                    match["before_count"])
                context.after_range = cls.mkrange(
                    match["after_start"],
                    match["after_count"])
                changes.append(
                    Change(
                        context.before_filename,
                        context.after_filename,
                        context.before_range,
                        context.after_range))
            elif match["removed_line"] is not None:
                assert changes
                changes[-1].removed_lines.append(match["removed_line"])
            else:
                assert match["added_line"] is not None
                assert changes
                changes[-1].added_lines.append(match["added_line"])
        return changes

    @staticmethod
    def mkpath(filename: str) -> Optional[Path]:
        """
        Make a `Path` from a parsed filename for a `Change` constructor.
        """
        if filename == "/dev/null":
            path = None
        else:
            # strip leading component indicating owner
            path = Path(os.path.join(*Path(filename).parts[1 :]))
        return path

    @staticmethod
    def mkrange(
            start: Union[int,
                         str],
            count: Optional[Union[int,
                                  str]]) -> range:
        """
        Make a `range` from a parsed range for a `Change` constructor.
        """
        if count is None:
            count = 1
        start = int(start)
        count = int(count)
        return range(start, start + count)
