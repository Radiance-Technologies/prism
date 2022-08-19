"""
Defines the base class and interface for all switch managers.
"""
import abc
from typing import Iterable, Optional, Set, Tuple

from prism.util.opam import OpamSwitch, VersionConstraint
from prism.util.radpytools import cachedmethod

from .exception import UnsatisfiableConstraints

PackageConstraint = Tuple[str, Optional[VersionConstraint]]


class SwitchManager(abc.ABC):
    """
    A basic manager that keeps a constant set of switches.
    """

    def __init__(
            self,
            initial_switches: Optional[Iterable[OpamSwitch]] = None) -> None:
        if initial_switches is None:
            initial_switches = []
        self._switches = set(initial_switches)

    @cachedmethod
    def _get_switch_config(
            self,
            switch: OpamSwitch) -> OpamSwitch.Configuration:
        return switch.export()

    @property
    def switches(self) -> Set[OpamSwitch]:
        """
        Get the set of switches managed by this instance.
        """
        return self._switches

    def get_switch(
            self,
            required_packages: Iterable[PackageConstraint]) -> OpamSwitch:
        """
        Get a switch that satifies the current constraints.

        Parameters
        ----------
        required_packages : Iterable[PackageConstraint]
            A set of required packages and their version constraints.

        Returns
        -------
        OpamSwitch
            A switch that provides the required packages.

        Raises
        ------
        UnsatisfiableConstraints
            If no switch managed by this instance can satisfy the
            constraints.
        """
        for switch in self.switches:
            if self.satisfies(switch, required_packages):
                return switch
        raise UnsatisfiableConstraints()

    def release_switch(self, switch: OpamSwitch) -> None:
        """
        Record that a client is no longer using the given switch.

        Parameters
        ----------
        switch : OpamSwitch
            A switch that was presumably retrieved via `get_switch` with
            a previous client request.
        """
        pass

    @cachedmethod
    def satisfies(
            self,
            switch: OpamSwitch,
            required_packages: Iterable[PackageConstraint]) -> bool:
        """
        Return whether the given switch satisifes the given constraints.

        Parameters
        ----------
        switch : OpamSwitch
            An existing switch.
        required_packages : Iterable[Tuple[str, VersionConstraint]]
            A set of required packages and their version constraints.

        Returns
        -------
        bool
            Whether the `switch` satisfies the given constraints.
        """
        config: OpamSwitch.Configuration = self._get_switch_config(switch)
        installed = dict(config.installed)
        for package_name, constraint in required_packages:
            try:
                installed_version = installed[package_name]
            except KeyError:
                return False
            else:
                if installed_version not in constraint:
                    return False
        return True
