"""
Defines an interface for programmatically querying OPAM.
"""
import logging
import pathlib
import re
import shutil
import subprocess
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from typing import ClassVar, Generator, Optional, Union

from .switch import OpamSwitch
from .version import OCamlVersion, Version

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


@dataclass
class OpamAPI:
    """
    Provides methods for querying the OCaml package manager.

    Note that OPAM must be installed to use all of the features of this
    class.

    .. warning::
        This class does not yet fully support the full expressivity of
        OPAM dependencies as documented at
        https://opam.ocaml.org/blog/opam-extended-dependencies/.
    """

    _SWITCH_INSTALLED_ERROR: ClassVar[
        str] = "[ERROR] There already is an installed switch named"
    active_switch: ClassVar[OpamSwitch] = OpamSwitch()

    @classmethod
    def create_switch(
            cls,
            switch_name: str,
            compiler: Union[str,
                            Version],
            opam_root: Optional[PathLike] = None) -> OpamSwitch:
        """
        Create a new switch.

        If a switch with the desired name already exists, then this
        function has no effect.

        Parameters
        ----------
        switch_name : str
            The name of the desired switch.
        compiler : Union[str, Version]
            A version of the OCaml compiler on which to base the switch.

        Returns
        -------
        OpamSwitch
            The created switch.


        Raises
        ------
        subprocess.CalledProcessError
            If the ``opam switch create`` command fails.
        VersionParseError
            If `compiler` is not a valid version identifier.

        Warns
        -----
        UserWarning
            If a switch with the given name already exists.
        """
        if isinstance(compiler, str):
            compiler = OCamlVersion.parse(compiler)
        command = f'opam switch create {switch_name} {compiler}'
        r = cls.run(command, check=False, opam_root=opam_root)
        if (r.returncode == 2
                and any(ln.strip().startswith(cls._SWITCH_INSTALLED_ERROR)
                        for ln in r.stderr.splitlines())):
            warning = f"opam: the switch {switch_name} already exists"
            warnings.warn(warning)
            logger.log(logging.WARNING, warning)
            return OpamSwitch(switch_name, opam_root)
        OpamSwitch.check_returncode(command, r)
        return OpamSwitch(switch_name, opam_root)

    @classmethod
    def clone_switch(
            cls,
            switch_name: str,
            clone_name: str,
            opam_root: Optional[PathLike] = None) -> None:
        """
        Clone the indicated switch.

        Parameters
        ----------
        switch_name : str
            The name of an existing switch to clone,
            belonging to the active root.
        clone_name : str
            The name to use for the cloned switch. 
        
        Returns
        -------
        OpamSwitch
            The cloned switch.

        Raises
        ------
        ValueError
            switch_name doesn't exist
        or: clone_name already exists
        or: an invalid switch name was passed in
        """
        # assuming we aren't on windows.
        # if we are, this is difficult because the opam manual
        # doesn't even say where the default opam root should be.
        current_opam_root = pathlib.Path(opam_root
                                      or cls.active_switch.root
                                      or "~/.opam/").expanduser()


        destination = current_opam_root/clone_name

        if len(destination.parents)!=len(current_opam_root.parents)+1:
            raise ValueError(f"{clone_name} is a path, \
                              not the name of a switch.")

        # we have to be extremely here.
        # if someone asked for a switch with the name "config"
        # and we carelessly deleted whatever was called "config",
        # it would brick the switch.
        if destination.exists():
            raise ValueError("The proposed switch name already exists \
                              or there's a file with that name. \
                              Won't delete existing files.")

        source = current_opam_root/switch_name

        if len(source.parents)!=len(current_opam_root.parents)+1:
            raise ValueError("f{switch_name} is a path, \
                              not the name of a switch.")

        if not source.is_dir():
            raise ValueError(f"Source switch {switch_name} doesn't \
                               exist in {current_opam_root}.")

        shutil.copytree(source,destination,symlinks=True)
        
        return OpamSwitch(clone_name,str(current_opam_root))


    @classmethod
    def remove_switch(
            cls,
            switch: Union[str,
                          OpamSwitch],
            opam_root: Optional[PathLike] = None) -> None:
        """
        Remove the indicated switch.

        Parameters
        ----------
        switch_name : str
            The name of an existing switch.

        Raises
        ------
        subprocess.CalledProcessError
            If the `opam switch remove` command fails, e.g., if the
            indicated switch does not exist.
        """
        if isinstance(switch, OpamSwitch):
            switch = switch.name
        cls.run(f'opam switch remove {switch} -y', opam_root=opam_root)

    @classmethod
    def run(
            cls,
            command: str,
            check: bool = True,
            opam_root: Optional[PathLike] = None
    ) -> subprocess.CompletedProcess:
        """
        Run a given command in the active switch and check for errors.
        """
        if opam_root is not None:
            command = f"{command} --root={opam_root}"
        return cls.active_switch.run(command, check)

    @classmethod
    def set_switch(
            cls,
            switch_name: Optional[str],
            opam_root: Optional[PathLike] = None) -> OpamSwitch:
        """
        Set the currently active switch to the given one.

        Parameters
        ----------
        switch_name : str | None
            The name of an existing switch or None if one wants to
            restore the global switch.
        opam_root : Optional[str], optional
            The root path, by default None
            Equivalent to setting ``$OPAMROOT`` to `opam_root` for the
            duration of the command.

        Raises
        ------
        subprocess.CalledProcessError
            If the `opam env` comand fails, e.g., if the indicated
            switch does not exist.
        """
        cls.active_switch = OpamSwitch(switch_name, opam_root)

    @classmethod
    def show_switch(cls) -> str:
        """
        Get the name of the current switch.

        Returns
        -------
        str
            The name of the current switch.

        Raises
        ------
        subprocess.CalledProcessError
            If the `opam switch show` command fails.
        """
        return cls.active_switch.name

    @classmethod
    @contextmanager
    def switch(
            cls,
            switch_name: str,
            opam_root: Optional[PathLike] = None) -> Generator[None,
                                                               None,
                                                               None]:
        """
        Get a context in which the given switch is active.

        The previously active switch is restored at the context's exit.
        """
        current_switch = cls.active_switch
        try:
            cls.set_switch(switch_name, opam_root)
            yield
        finally:
            cls.set_switch(current_switch.name, current_switch.root)
