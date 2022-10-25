"""
Supply a protocol for serializable data.
"""

import os
from typing import Optional, Protocol

import seutil as su


class Serializable(Protocol):
    """
    A simple protocol for serializable data.
    """

    def dump(
            self,
            output_filepath: os.PathLike,
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> None:
        """
        Serialize data to text file.

        Parameters
        ----------
        output_filepath : os.PathLike
            Filepath to which cache should be dumped.
        fmt : su.io.Fmt, optional
            Designated format of the output file,
            by default `su.io.Fmt.yaml`.
        """
        su.io.dump(output_filepath, self, fmt=fmt)

    @classmethod
    def load(
            cls,
            filepath: os.PathLike,
            fmt: Optional[su.io.Fmt] = None) -> 'Serializable':
        """
        Load a serialized object from file..

        Parameters
        ----------
        filepath : os.PathLike
            Filepath containing repair mining cache.
        fmt : Optional[su.io.Fmt], optional
            Designated format of the input file, by default None.
            If None, then the format is inferred from the extension.

        Returns
        -------
        Serializable
            The deserialized object.
        """
        return su.io.load(filepath, fmt, clz=cls)
