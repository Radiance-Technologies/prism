"""
Defines an adaptive switch manager introduces new switches on demand.
"""

import tempfile
import time
from pathlib import Path
from typing import Optional

from prism.util.compare import Top
from prism.util.opam import (
    AssignedVariables,
    OpamAPI,
    OpamSwitch,
    PackageFormula,
)
from prism.util.radpytools.multiprocessing import synchronizedmethod

from .base import SwitchManager
from .exception import UnsatisfiableConstraints


class AdaptiveSwitchManager(SwitchManager):
    """
    A manager that creates switches as needed to satisfy constraints.

    Newly introduced switches are always based off of an existing
    switch.

    .. warning::
        Careless use of this utility can consume significant disk space
        as each switch may be hundreds of megabytes or greater in size.

    Parameters
    ----------
    initial_switches : Optional[Iterable[OpamSwitch]], optional
        Zero or more preconstructed switches with which to initialize
        the manager.
    variables : Optional[AssignedVariables], optional
        Optional variables that may impact the interpretation of any
        formula evaluated by the switch.
    """

    def __init__(self, *args, max_pool_size=1000, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._temporary_switches = set()
        self._last_used = {}
        self._max_pool_size = max_pool_size

    def _clone_switch(self, switch: OpamSwitch) -> OpamSwitch:
        """
        Clone the given switch.
        """
        prefix = switch.name.split("_clone_")[-1]
        prefix = f"{prefix}_clone_"
        with tempfile.TemporaryDirectory(prefix=prefix, dir=switch.root) as d:
            clone_dir = Path(d)
        clone = OpamAPI.clone_switch(switch.name, clone_dir.name, switch.root)
        # it's okay if this is clobbered by multiple threads.
        # if a clobber occurs, the times must have been CLOSE.
        self._last_used[switch] = time.time()
        return clone

    def get_switch(
            self,
            formula: PackageFormula,
            variables: Optional[AssignedVariables] = None) -> OpamSwitch:
        """
        Get a switch that satisfies the given constraints.

        If no existing managed switch satifies the formula but could do
        so with the installation of new packages, then a satisfactory
        switch is created from an existing one and added to the
        manager's pool of switches.

        Parameters
        ----------
        formula : PackageFormula
            A formula expressing required packages and their version
            constraints.
        variables : Optional[AssignedVariables], optional
            Optional variables that may impact the interpretation of the
            formula and override the manager's preset variables.

        Returns
        -------
        OpamSwitch
            A switch that provides the required packages.
            The switch is a temporary clone of a managed switch, thus
            ensuring that repeated calls to `get_switch` yield isolated
            sandboxes.

        Raises
        ------
        UnsatisfiableConstraints
            If it is not possible to extend an existing switch to
            satisfy the formula.
        """
        self._lock.acquire()

        if (variables is None):
            # default is no variables
            variables = {}

        closest_switch = None
        minimum_size = Top()
        for switch in self.switches:
            simplified = self.simplify(switch, formula, **variables)
            if isinstance(simplified, bool):
                if simplified:
                    simplified_size = 0
                else:
                    continue
            else:
                simplified_size = simplified.size
            if simplified_size < minimum_size:
                closest_switch = switch
                minimum_size = simplified_size
            if simplified_size == 0:
                break
        # clone the closest switch
        if closest_switch is None:
            raise UnsatisfiableConstraints(formula)
        if minimum_size > 0:
            # add a new switch to the persistent pool
            self._lock.release()
            clone = self._clone_switch(switch)
            clone.install_formula(formula)
            self._lock.acquire()
            self.switches.add(clone)
            if (len(self.switches) > self._max_pool_size):
                self._evict()
            switch = clone
        # return a temporary clone
        self._lock.release()
        clone = self._clone_switch(switch)
        self._lock.acquire()
        self._temporary_switches.add(clone)
        self._lock.release()
        return clone

    @synchronizedmethod
    def release_switch(self, switch: OpamSwitch) -> None:
        """
        Record that a client is no longer using the given switch.

        If the switch is a clone returned by `get_switch`, then it is
        deleted.

        Parameters
        ----------
        switch : OpamSwitch
            A switch that was presumably retrieved via `get_switch` with
            a previous client request.
        """
        if switch in self._temporary_switches:
            assert switch.is_clone
            self._temporary_switches.discard(switch)
            OpamAPI.remove_switch(switch)

    @synchronizedmethod
    def _evict(self):
        """
        Pick a persistent switch to remove and remove it.

        Picks by least recently used.
        """
        disqualified_switches = set()

        for switch in self._last_used:
            if (switch not in self.switches
                    or switch in self._temporary_switches
                    or not switch.is_clone):
                disqualified_switches.add(switch)

        for switch in disqualified_switches:
            del self._last_used[switch]

        if (len(self._last_used) == 0):
            # nothing to remove
            return

        lru = sorted(self._last_used, key=lambda x: self._last_used[x])[0]

        OpamAPI.remove_switch(lru)

        self.switches.remove(lru)

        return
