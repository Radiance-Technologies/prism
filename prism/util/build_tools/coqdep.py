"""
Provides an object-oriented abstraction of OPAM switches.
"""
from os import PathLike
from typing import List, Optional

from prism.util.opam.switch import OpamSwitch


class CoqDepAPI:
    """
    Wrapper for the Coq build utility `coqdep`.

    Note that Coq must be installed to use all of the features of this
    class.
    """
    def __init__(self):
        self.test_val = ""

    def order_dependencies(
            self,
            files: List[PathLike],
            switch: OpamSwitch,
            IQR: Optional[str] = ''):
        """
        Return sorted dependencies for supplied files.

        Parameters
        ----------
        files : List[PathLike]
        List of files to be submitted to coqdep

        switch : OpamSwitch
        Used for execution of coqdep in the proper environment

        IQR : Optional[str]
        IQR flags for coqdep

        Returns
        -------
        file_deps : List[str]
        List of '.vo' files in order of least to most dependent
        """
        files = ' '.join(files)
        command = "coqdep {0} -sort {1}".format(files, IQR)
        file_deps = switch.run(command)
        file_deps = file_deps.stdout.strip().split(" ")
        return file_deps
