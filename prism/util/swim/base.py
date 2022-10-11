"""
Defines the base class and interface for all switch managers.
"""

from multiprocessing import RLock
from typing import Dict, Iterable, Optional, Set, Union

from prism.util.opam import AssignedVariables, OpamSwitch, PackageFormula
from prism.util.radpytools import cachedmethod
from prism.util.radpytools.multiprocessing import (
    synchronizedmethod,
    synchronizedproperty,
)

from .exception import UnsatisfiableConstraints


class SwitchManager:
    """
    A basic manager that keeps a constant set of switches.

    The switches are assumed to be managed exclusively by the
    `SwitchManager` for the duration of execution so that it can cache
    repeated queries for faster operation.

    Parameters
    ----------
    initial_switches : Optional[Iterable[OpamSwitch]], optional
        Zero or more preconstructed switches with which to initialize
        the manager.
    variables : Optional[AssignedVariables], optional
        Optional variables that may impact the interpretation of any
        formula evaluated by the switch.
    """

    def __init__(
            self,
            initial_switches: Optional[Iterable[OpamSwitch]] = None,
            variables: Optional[AssignedVariables] = None) -> None:
        if initial_switches is None:
            initial_switches = []
        if variables is None:
            variables = {}
        self._switches = set(initial_switches)
        self._variables = dict(variables)
        self._lock = RLock()

    @cachedmethod
    @synchronizedmethod(semlock_name="_lock")
    def _get_switch_config(
            self,
            switch: OpamSwitch) -> OpamSwitch.Configuration:
        return switch.export()

    @synchronizedproperty(semlock_name="_lock")
    def switches(self) -> Set[OpamSwitch]:
        """
        Get the set of switches managed by this instance.
        """
        return self._switches

    @synchronizedproperty(semlock_name="_lock")
    def variables(self) -> Dict[str, Union[bool, int, str]]:
        """
        Get the set of package variables used to evaluate dependencies.
        """
        return self._variables

    @synchronizedmethod(semlock_name="_lock")
    def get_switch(
            self,
            formula: PackageFormula,
            variables: Optional[AssignedVariables] = None) -> OpamSwitch:
        """
        Get a switch that satifies the given constraints.

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

        Raises
        ------
        UnsatisfiableConstraints
            If no switch managed by this instance can satisfy the
            constraints.
        """
        if variables is None:
            variables = {}
        for switch in self.switches:
            if self.satisfies(switch, formula, **variables):
                return switch
        raise UnsatisfiableConstraints(formula)

    @synchronizedmethod(semlock_name="_lock")
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
    @synchronizedmethod(semlock_name="_lock")
    def satisfies(
            self,
            switch: OpamSwitch,
            formula: PackageFormula,
            **variables: AssignedVariables) -> bool:
        """
        Return whether the given switch satisfies the given constraints.

        Parameters
        ----------
        switch : OpamSwitch
            An existing switch.
        formula : Iterable[Tuple[str, VersionConstraint]]
            A formula expressing required packages and their version
            constraints.
        variables : AssignedVariables
            Optional variables that may impact the interpretation of the
            formula and override the manager's preset variables.

        Returns
        -------
        bool
            Whether the `switch` satisfies the given constraints.
        """
        active_variables = dict(self.variables)
        active_variables.update(variables)
        config: OpamSwitch.Configuration = self._get_switch_config(switch)
        return formula.is_satisfied(dict(config.installed), active_variables)

    @cachedmethod
    @synchronizedmethod(semlock_name="_lock")
    def simplify(
            self,
            switch: OpamSwitch,
            formula: PackageFormula,
            **variables: AssignedVariables) -> Union[bool,
                                                     PackageFormula]:
        """
        Simplify a formula using a switch's installed packages.

        Parameters
        ----------
        switch : OpamSwitch
            An existing switch.
        formula : PackageFormula
            A formula expressing required packages and their version
            constraints.
        variables : AssignedVariables
            Optional variables that may impact the interpretation of the
            formula and override the manager's preset variables.

        Returns
        -------
        Union[bool, PackageFormula]
            The simplified formula.

        See Also
        --------
        PackageFormula.simplify : For more details on simplification.
        """
        active_variables = dict(self.variables)
        active_variables.update(variables)
        config: OpamSwitch.Configuration = self._get_switch_config(switch)
        # config.installed can be (and was) None
        return formula.simplify(dict(config.installed), active_variables)
