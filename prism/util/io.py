"""
Provides utility functions for serialized data files.
"""
import os
import tempfile
import typing
from enum import Enum
from pathlib import Path
from typing import IO, TYPE_CHECKING, Optional, Union

import seutil as su
import ujson
import yaml
from seutil.io import FmtProperty

if TYPE_CHECKING:
    from prism.util.serialize import Serializable


class Fmt(FmtProperty, Enum):
    """
    A variant of `su.io.Fmt` with faster YAML and JSON formatters.

    To be used as a drop-in replacement, stymied somewhat by the fact
    that enums cannot be subclassed. Use `typing.cast` where necessary
    to convince type checkers that this is the original `su.io.Fmt`
    class.
    """

    txt = su.io.Fmt.txt
    pickle = su.io.Fmt.pickle
    json = FmtProperty(
        writer=lambda f,
        obj: ujson.dump(obj,
                        typing.cast(IO[str],
                                    f),
                        sort_keys=True),
        reader=lambda f: ujson.load(typing.cast(IO[str],
                                                f)),
        serialize=True,
        exts=["json"],
    )
    jsonFlexible = json._replace(
        reader=lambda f: yaml.load(f,
                                   Loader=yaml.CLoader))
    """
    A variant of `json` that allows formatting errors (e.g., trailing
    commas), but cannot handle unprintable chars.
    """
    jsonPretty = json._replace(
        writer=lambda f,
        obj: ujson.dump(obj,
                        f,
                        sort_keys=True,
                        indent=4),
    )
    """
    A variant of `json` that pretty-prints with sorted keys.
    """
    jsonNoSort = json._replace(
        writer=lambda f,
        obj: ujson.dump(obj,
                        f,
                        indent=4),
    )
    """
    A variant of `json` that pretty-prints without sorted keys.
    """
    jsonList = FmtProperty(
        writer=lambda item: ujson.dumps(item),
        reader=lambda line: ujson.loads(typing.cast(str,
                                                    line)),
        exts=["jsonl"],
        line_mode=True,
        serialize=True,
    )
    """
    A variant of JSON that dumps to and from a string.
    """
    txtList = su.io.Fmt.txtList
    yaml = FmtProperty(
        writer=lambda f,
        obj: yaml.dump(
            obj,
            f,
            encoding="utf-8",
            default_flow_style=False,
            Dumper=yaml.CDumper),
        reader=lambda f: yaml.load(f,
                                   Loader=yaml.CLoader),
        serialize=True,
        exts=["yml",
              "yaml"],
    )
    csvList = su.io.Fmt.csvList


def infer_fmt_from_ext(ext: str, default: Optional[Fmt] = None) -> Fmt:
    """
    Infer a `Fmt` from a file extension.

    To be used as a drop in replacement for `su.io.infer_fmt_from_ext`.
    """
    if ext.startswith("."):
        ext = ext[1 :]

    for fmt in Fmt:
        if fmt.exts is not None and ext in fmt.exts:
            return fmt

    if default is not None:
        return default
    else:
        raise RuntimeError(f'Cannot infer format for extension "{ext}"')


def infer_format(filepath: os.PathLike) -> Fmt:
    """
    Infer format for loading serialized data.

    Parameters
    ----------
    filepath : os.PathLike
        A filepath to a file containing serialized data.

    Returns
    -------
    Fmt
        `seutil` format to handle loading files based on format.

    Raises
    ------
    ValueError
        Exception is raised when file extension of `filepath` is
        not an extension supported by any `Fmt` format.

    See Also
    --------
    Fmt
        Each enumeration value has a list of valid extensions under
        the ``Fmt.<name>.exts`` attribute.

    Notes
    -----
    If multiple ``Fmt`` values have the same extensions,
    (i.e. json, jsonFlexible, jsonPretty, jsonNoSort), the first
    value defined in ``Fmt`` will be used.
    """
    formatter: Optional[Fmt]
    formatter = None
    extension = os.path.splitext(filepath)[-1].strip(".")
    for fmt in Fmt:
        if extension in fmt.exts:
            formatter = fmt
            # Break early, ignore other formatters that may support
            # the extension.
            break
    assert formatter is not None
    if formatter is None:
        raise ValueError(
            f"Filepath ({filepath}) has unknown extension ({extension})")
    return formatter


def atomic_write(
        full_file_path: Path,
        file_contents: Union[str,
                             'Serializable']):
    r"""
    Write a message or object to a text file.

    Any existing file contents are overwritten.

    Parameters
    ----------
    full_file_path : Path
        Full file path, including directory, filename, and extension, to
        write to
    file_contents : Union[str, Serializable]
        The contents to write or serialized to the file.

    Raises
    ------
    TypeError
        If `file_contents` is not a string or `Serializable`.
    """
    # TODO: Refactor to avoid circular import
    from prism.util.serialize import Serializable
    if not isinstance(file_contents, (str, Serializable)):
        raise TypeError(
            f"Cannot write object of type {type(file_contents)} to file")
    fmt_ext = full_file_path.suffix  # contains leading period
    directory = full_file_path.parent
    if not directory.exists():
        os.makedirs(str(directory))
    # Ensure that we write atomically.
    # First, we write to a temporary file so that if we get
    # interrupted, we aren't left with a corrupted file.
    with tempfile.NamedTemporaryFile("w",
                                     delete=False,
                                     dir=directory,
                                     encoding='utf-8') as f:
        if isinstance(file_contents, str):
            f.write(file_contents)
    if isinstance(file_contents, Serializable):
        fmt = infer_fmt_from_ext(fmt_ext)
        file_contents.dump(f.name, fmt)
    # Then, we atomically move the file to the correct, final
    # path.
    os.replace(f.name, full_file_path)
