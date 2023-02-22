"""
Provides utility functions for serialized data files.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional, Union

import seutil as su

from prism.util.serialize import Serializable


def infer_format(filepath: os.PathLike) -> su.io.Fmt:
    """
    Infer format for loading serialized data.

    Parameters
    ----------
    filepath : os.PathLike
        A filepath to a file containing serialized data.

    Returns
    -------
    su.io.Fmt
        `seutil` format to handle loading files based on format.

    Raises
    ------
    ValueError
        Exception is raised when file extension of `filepath` is
        not an extension supported by any `su.io.Fmt` format.

    See Also
    --------
    su.io.Fmt :
        Each enumeration value has a list of valid extensions under
        the ``su.io.Fmt.<name>.exts`` attribute.

    Notes
    -----
    If multiple ``su.io.Fmt`` values have the same extensions,
    (i.e. json, jsonFlexible, jsonPretty, jsonNoSort), the first
    value defined in ``su.io.Fmt`` will be used.
    """
    formatter: su.io.Fmt
    extension = os.path.splitext(filepath)[-1].strip(".")
    for fmt in su.io.Fmt:
        if extension in fmt.exts:
            formatter = fmt
            # Break early, ignore other formatters that may support
            # the extension.
            break
    if formatter is None:
        raise ValueError(
            f"Filepath ({filepath}) has unknown extension ({extension})")
    return formatter


def atomic_write(full_file_path: Path,
                 file_contents: Union[str,
                                      Serializable]) -> Optional[str]:
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
    if not isinstance(file_contents, (str, Serializable)):
        raise TypeError(
            f"Cannot write object of type {type(file_contents)} to file")
    fmt_ext = full_file_path.suffix  # contains leading period
    fmt = su.io.infer_fmt_from_ext(fmt_ext)
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
        file_contents.dump(f.name, fmt)
    # Then, we atomically move the file to the correct, final
    # path.
    os.replace(f.name, full_file_path)
