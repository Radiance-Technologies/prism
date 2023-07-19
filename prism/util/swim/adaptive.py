"""
Defines an adaptive switch manager introduces new switches on demand.
"""

import os
import tempfile
import time
from pathlib import Path
from subprocess import CalledProcessError
from typing import Dict, Optional, Set

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
        self._temporary_switches: Set[OpamSwitch] = set()
        self._last_used: Dict[OpamSwitch,
                              float] = {}
        self._max_pool_size = max_pool_size

    @synchronizedmethod(semlock_name="_lock")
    def _add_managed_switch(self, switch: OpamSwitch) -> None:
        """
        Add a switch to the managed pool.

        Parameters
        ----------
        switch : OpamSwitch
            An opam switch whose management should be given to this
            `SwitchManager`.

        Notes
        -----
        If the pool exceeds its maximum capacity after the addition of
        the `switch`, then a switch will be automatically removed.
        A removed switch is irreversibly deleted.
        In certain circumstances, this may include the `switch` just
        added, thus rendering the object invalid.
        """
        self._last_used[switch] = time.time()
        self.switches.add(switch)
        if (len(self.switches) > self._max_pool_size):
            self._evict()

    def _clone_switch(self, switch: OpamSwitch) -> OpamSwitch:
        """
        Clone the given switch.
        """
        prefix = switch.name.split("_clone_")[-1]
        prefix = f"{prefix}_clone_"
        with tempfile.TemporaryDirectory(prefix=prefix, dir=switch.root) as d:
            clone_dir = Path(d)
        clone = OpamAPI.clone_switch(switch.name, clone_dir.name, switch.root)
        return clone

    @synchronizedmethod(semlock_name="_lock")
    def _evict(self) -> None:
        """
        Pick a persistent switch to remove and remove it.

        Picks by least recently used. Note that the switch is not simply
        removed from the managed pool but is instead deleted from the
        filesystem. This action cannot be undone.
        """
        # limit consideration only to switches in the managed pool that
        # are not clones
        disqualified_switches = set()

        for switch in self._last_used:
            if (switch not in self.switches
                    or switch in self._temporary_switches
                    or not switch.is_clone):
                disqualified_switches.add(switch)

        for switch in disqualified_switches:
            self._last_used.pop(switch)

        if (len(self._last_used) == 0):
            # nothing to remove
            return

        lru = sorted(self._last_used, key=lambda x: self._last_used[x])[0]
        switch_path = lru.path

        OpamAPI.remove_switch(lru)

        # leave an empty placeholder directory stub to ensure that
        # subsequent clones with generated tempfile names do not clash
        # with previously evicted ones, thus potentially leading to
        # incorrect behavior in cached methods
        os.makedirs(switch_path)

        self._last_used.pop(lru)
        self.switches.remove(lru)

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
        with self._lock:
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
            clone = self._clone_switch(closest_switch)
            try:
                clone.install_formula(
                    formula,
                    criteria="-changed,+removed,-notuptodate")
            except CalledProcessError:
                # This exception almost certainly means the Coq version
                # can't be satisfied. So, clean up the clone and report
                # the error.
                OpamAPI.remove_switch(clone)
                raise UnsatisfiableConstraints(formula)
            else:
                self._add_managed_switch(clone)
                # make sure clone was not evicted
                if clone.exists:
                    closest_switch = clone
        # return a temporary clone
        clone = self._clone_switch(closest_switch)
        with self._lock:
            self._temporary_switches.add(clone)
        return clone

    @synchronizedmethod(semlock_name="_lock")
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
