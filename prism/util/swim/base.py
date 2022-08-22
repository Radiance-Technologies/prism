"""
Defines the base class and interface for all switch managers.
"""
import abc
from typing import Dict, Iterable, Mapping, Optional, Set, Tuple, Union

from prism.util.opam import OpamSwitch, VersionConstraint
from prism.util.opam.formula import PackageFormula
from prism.util.radpytools import cachedmethod

from .exception import UnsatisfiableConstraints

PackageConstraint = Tuple[str, Optional[VersionConstraint]]


class SwitchManager(abc.ABC):
    """
    A basic manager that keeps a constant set of switches.
    """

    def __init__(
        self,
        initial_switches: Optional[Iterable[OpamSwitch]] = None,
        variables: Optional[Mapping[str,
                                    Union[bool,
                                          int,
                                          str]]] = None) -> None:
        if initial_switches is None:
            initial_switches = []
        if variables is None:
            variables = {}
        self._switches = set(initial_switches)
        self._variables = dict(variables)

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

    @property
    def variables(self) -> Dict[str, Union[bool, int, str]]:
        """
        Get the set of package variables used to evaluate dependencies.
        """
        return self._variables

    def get_switch(
        self,
        formula: PackageFormula,
        variables: Optional[Mapping[str,
                                    Union[bool,
                                          int,
                                          str]]] = None
    ) -> OpamSwitch:
        """
        Get a switch that satifies the current constraints.

        Parameters
        ----------
        required_packages : Iterable[PackageConstraint]
            A set of required packages and their version constraints.
        variables : Mapping[str, Union[bool, int, str]] | None, optional
            Optional variables that may impact the interpretation of the
            formula and override the manager's preset variables.

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
            if self.satisfies(switch, formula, variables):
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
        formula: PackageFormula,
        variables: Optional[Mapping[str,
                                    Union[bool,
                                          int,
                                          str]]] = None) -> bool:
        """
        Return whether the given switch satisifes the given constraints.

        Parameters
        ----------
        switch : OpamSwitch
            An existing switch.
        formula : Iterable[Tuple[str, VersionConstraint]]
            A formula expressing the required packages and their
            version constraints.
        variables : Mapping[str, Union[bool, int, str]] | None, optional
            Optional variables that may impact the interpretation of the
            formula and override the manager's preset variables.

        Returns
        -------
        bool
            Whether the `switch` satisfies the given constraints.
        """
        if variables is not None:
            variables = {}
        active_variables = dict(self.variables)
        active_variables.update(variables)
        config: OpamSwitch.Configuration = self._get_switch_config(switch)
        return formula.is_satisfied(dict(config.installed), active_variables)
