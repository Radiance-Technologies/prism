"""
Defines an interface for programmatically querying OPAM.
"""
import logging
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

    This class and its counterpart `OpamSwitch` each maintain the global
    environment as an invariant, i.e., neither ever sets, removes, or
    modifies any environment variables.

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
        ParseError
            If `compiler` is not a valid version identifier.

        Warns
        -----
        UserWarning
            If a switch with the given name already exists.
        """
        if isinstance(compiler, str):
            # validate string is a version of OCaml
            compiler = OCamlVersion.parse(compiler)
        compiler = f"ocaml-base-compiler.{compiler}"
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
            opam_root: Optional[PathLike] = None) -> OpamSwitch:
        """
        Clone the indicated switch.

        .. warning::
            Cloning switches is an unsafe optimization and one should
            generally not interact with any switches produced in this
            manner outside the context of `OpamAPI` and `OpamSwitch`.

        Parameters
        ----------
        switch_name : str
            The name of an existing switch to clone,
            belonging to the active root.
        clone_name : str
            The name to use for the cloned switch.
        opam_root : Optional[PathLike]
            The root of the existing switch and the resulting clone.
            Support for clones at different roots is currently not
            available.

        Returns
        -------
        OpamSwitch
            The cloned switch.

        Raises
        ------
        ValueError
            If `switch_name` is not the name of any existing switch or
            `clone_name` already exists or is otherwise invalid.
        """
        # validates that the source switch exists as side-effect
        origin = OpamSwitch(switch_name, opam_root)
        opam_root = origin.root

        destination = OpamSwitch.get_root(opam_root, clone_name)

        # we have to be extremely careful here.
        # if someone asked for a switch with the name "config"
        # and we carelessly deleted whatever was called "config",
        # it would brick the switch.
        if destination.exists():
            raise ValueError(
                f"The proposed switch name '{clone_name}' already exists"
                " or there's a file with that name.")

        shutil.copytree(origin.path, destination, symlinks=True)

        return OpamSwitch(clone_name, opam_root)

    @classmethod
    def remove_switch(
            cls,
            switch: Union[str,
                          OpamSwitch],
            opam_root: Optional[PathLike] = None) -> None:
        """
        Remove the indicated switch.

        .. warning::
            Some switches are used as mountpoints for their clones.
            If the original is deleted, then an empty directory will be
            created as a mountpoint for the clones, which will prevent
            you from creating a new switch with the old name.
            Therefore, one must ensure that originals are not deleted
            independently of their clones.

        Parameters
        ----------
        switch_name : str
            The name of an existing switch.

        Raises
        ------
        ValueError
            If the indicated switch does not exist.
        """
        if isinstance(switch, OpamSwitch):
            opam_root = opam_root or switch.root
            switch = switch.name
        # validate switch exists
        switch = OpamSwitch(switch, opam_root)
        opam_root = switch.root

        if switch.is_clone:
            # This is a clone, not a registered existing switch.
            # Opam will refuse to remove it.
            # Delete the associated directory, taking care not to delete
            # (follow) any symlinks.
            shutil.rmtree(switch.path)
        else:
            cls.run(f'opam switch remove {switch.name} -y', opam_root=opam_root)

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
        ValueError
            If the indicated switch does not exist.
        """
        cls.active_switch = OpamSwitch(switch_name, opam_root)

    @classmethod
    def show_root(cls) -> PathLike:
        """
        Get the path of the current OPAM root.

        Returns
        -------
        str
            The path to the current OPAM root, i.e., the root that
            ``None`` resolves to when given as the value for `opam_root`
            in `create_switch`.
        """
        return cls.active_switch.root

    @classmethod
    def show_switch(cls) -> str:
        """
        Get the name of the current switch.

        Returns
        -------
        str
            The name of the current switch.
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
