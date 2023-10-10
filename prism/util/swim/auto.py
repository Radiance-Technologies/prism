#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Defines an adaptive switch manager that initializes itself.
"""

from pathlib import Path
from typing import Iterable, List, Optional

from prism.util.opam import AssignedVariables, OpamSwitch
from prism.util.opam.api import OpamAPI
from prism.util.radpytools import PathLike

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
            variables: Optional[AssignedVariables] = None,
            **kwargs) -> None:
        if opam_roots is None:
            opam_roots = [OpamAPI.show_root()]
        switches = []
        for root in opam_roots:
            switches.extend(self.find_switches(root))
        super().__init__(switches, variables, **kwargs)

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
                    switch = OpamSwitch(potential_switch.name, root)
                except ValueError:
                    continue
                else:
                    switches.append(switch)
        return switches
