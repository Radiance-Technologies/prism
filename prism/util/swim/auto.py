"""
Defines an adaptive switch manager that initializes itself.
"""

from os import PathLike
from pathlib import Path
from typing import Iterable, List, Optional

from prism.util.opam import AssignedVariables, OpamSwitch

from .adaptive import AdaptiveSwitchManager


class AutoSwitchManager(AdaptiveSwitchManager):
    """
    An adaptive manager that is initialized from OPAM root directories.

    Parameters
    ----------
    opam_roots : Optional[Iterable[PathLike]], optional
        Zero or more root directories in which switches may be found,
        by default None.
        If None, then it defaults to the global "default" OPAM root.
    variables : Optional[AssignedVariables], optional
        Optional variables that may impact the interpretation of any
        formula evaluated by the switch.

    See Also
    --------
    AdaptiveSwitchManager : For more details.
    """

    def __init__(
            self,
            opam_roots: Optional[Iterable[PathLike]] = None,
            variables: Optional[AssignedVariables] = None) -> None:
        if opam_roots is None:
            opam_roots = []
        switches = []
        for root in opam_roots:
            switches.extend(self.find_switches(root))
        super().__init__(switches, variables)

    @classmethod
    def find_switches(cls, root: PathLike) -> List[OpamSwitch]:
        """
        Get the switches contained in the given OPAM root directory.

        Parameters
        ----------
        root : PathLike
            The path to a directory used as the presumptive root of any
            switches returned by this function.

        Returns
        -------
        List[OpamSwitch]
            The switches rooted at the given location.

        Raises
        ------
        ValueError
            If `root` is not a directory.
        """
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError(f"Expected a directory, got {root}")
        switches = []
        for potential_switch in root.iterdir():
            if potential_switch.is_dir():
                try:
                    switch = OpamSwitch(potential_switch.stem, root)
                except ValueError:
                    continue
                else:
                    switches.append(switch)
        return switches
