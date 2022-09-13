"""
A common interface for text-parseable classes.
"""
import abc
from typing import Any, Dict, Tuple, Union


class ParseError(Exception):
    """
    Raised when a string fails to parse to an instance of `Parseable`.
    """

    def __init__(self, tp: type, parsed: str) -> None:
        super().__init__()
        self.tp = tp
        self.parsed = parsed

    def __reduce__(self) -> Union[str, Tuple[type, str]]:  # noqa: D105
        return ParseError, (self.tp, self.parsed)

    def __str__(self) -> str:  # noqa: D105
        return f"Failed to parse {self.tp} from {self.parsed}"


class Parseable(abc.ABC):
    """
    Something that can be parsed from text.

    The chief method that must be implemented by any subclass is
    `_chain_parse`. In essence, this form of parsing is intended to
    perform a single scan across the input with minimal backtracks or
    buffering.
    """

    @classmethod
    @abc.abstractmethod
    def _chain_parse(cls, input: str, pos: int) -> Tuple['Parseable', int]:
        """
        Parse an instance of `cls` starting from the given position.

        Parameters
        ----------
        input : str
            A string beginning at `pos` with a representation of a `cls`
            instance.
        pos : int
            The position at which to start parsing.

        Returns
        -------
        Parseable
            The parsed `cls` instance.
        int
            The index of the first character after the text representing
            the parsed `cls` instance.

        Raises
        ------
        ValueError
            If an instance of `cls` cannot be parsed from the input
            starting at `pos`.
        """
        ...

    @classmethod
    def _consume(cls, input: str, pos: int, expected: str) -> int:
        """
        Parse the expected input but do not raise an error if not found.
        """
        try:
            return cls._expect(input, pos, expected, 0)
        except ParseError:
            return pos

    @classmethod
    def _expect(cls, input: str, pos: int, expected: str, begpos: int) -> int:
        """
        Parse the expected input and raise an error if not found.
        """
        for ec in expected:
            if pos >= len(input) or input[pos] != ec:
                raise ParseError(cls, input[begpos :])
            pos += 1
        return pos

    @classmethod
    def _lookback(cls, input: str, pos: int, count: int) -> Tuple[str, int]:
        """
        Get up to `count` prior, contiguous non-whitespace characters.
        """
        # strip whitespace
        pos -= 1
        while pos > 0 and input[pos].isspace():
            pos -= 1
        result = []
        for _ in range(count):
            if pos <= 0 or input[pos].isspace():
                break
            result.append(input[pos])
            pos -= 1
        return ''.join(reversed(result)), max(pos, 0)

    @classmethod
    def _lstrip(cls, input: str, pos: int) -> int:
        """
        Advance `pos` to the next non-whitespace character in `input`.
        """
        while pos < len(input) and input[pos].isspace():
            pos += 1
        return pos

    @classmethod
    def parse(
        cls,
        input: str,
        exhaustive: bool = True,
        lstrip: bool = True,
        pos: int = 0,
        **kwargs: Dict[str,
                       Any]) -> Union['Parseable',
                                      Tuple['Parseable',
                                            int]]:
        """
        Parse an instance of `cls`.

        By default, parsing is strict such that leading or trailing
        whitespace is not ignored.

        Parameters
        ----------
        input : str
            A string representation of a `cls` instance.
        exhaustive : bool, optional
            Whether to require parsing to the end of the entire `input`,
            by default True.
            If False, the position reached is returned.
        lstrip : bool, optional
            Whether to strip leading whitespace before parsing, by
            default False.
        pos : int, optional
            The character index at which to start parsing, by default
            zero.
        kwargs : Dict[str, Any], optional
            Optional keyword arguments to customize parsing.

        Returns
        -------
        Parseable
            An instance of `cls` corresponding to the `input`.
        int, optional
            The position reached at the end of parsing if `exhaustive`
            is False.

        Raises
        ------
        ParseError
            If the `input` cannot be parsed into an instance of `cls` or
            `exhaustive` is True and there is extra trailing input after
            any valid string representation of `cls`.
        """
        if lstrip:
            pos = cls._lstrip(input, pos)
        parsed, pos = cls._chain_parse(input, pos, **kwargs)
        if exhaustive:
            if pos < len(input):
                raise ParseError(cls, input[pos :])
            return parsed
        else:
            return parsed, pos
