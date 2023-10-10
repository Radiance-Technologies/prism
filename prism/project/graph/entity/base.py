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
Module for base node in project graph.
"""
import inspect
from abc import ABC, abstractmethod
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Set, Tuple, Type

from .type import DataDict


class ProjectEntityBase(ABC):
    """
    Abstract class containing methods to be implemented.
    """

    @abstractmethod
    def init_parent(self) -> 'ProjectEntityBase':
        """
        Initialize the parent entity this instance's attributes.
        """
        pass

    @abstractmethod
    def id_component(self) -> Tuple[str, str]:
        """
        Return unique identifier for entity.

        Return
        ------
        str:
            The label which will be placed in parantheses
            for this specific component of the entity id.
        str:
            The value that uniquely identifies this instance
            from other instances of the same class.
        """
        pass


class ProjectEntity(ProjectEntityBase):
    """
    An entity specific to a project.
    """

    def __init__(self, path: Path, **extra):
        """
        Initialize the project entity and its attributes.

        Parameters
        ----------
        path : Path
            A path that uniquely identifies a file the
            entity represents or is derived from.
        extra : Dict[str, Any]
            This dictionary will be added to the
            entity DataDict.
        """
        super().__init__()
        extra["typename"] = self.typename
        extra["type"] = self.type

        # Compute entity data
        #   1) Add Type information
        #   2) Add fields specific to this class.
        #   3) Add extra arguments passed on initialization.
        data = {
            "type": self.__class__,
            "typename": self.__class__.__name__,
        }
        for name in self.not_inherited_fields():
            data[name] = getattr(self, name)
        data.update(extra)

        # Compute entity_id by concatenating each super class's id
        # component together in reverse MRO order.
        # ProjectEntity is removed from the MRO order.
        mro = reversed(inspect.getmro(self.__class__))
        type_sequence = [cls for cls in mro if issubclass(cls, ProjectEntity)]
        type_sequence.pop(0)
        if self.__class__ not in type_sequence:
            type_sequence = type_sequence + [self.__class__]

        def make_id(label, value):
            return f"({label}) {value}"

        entity_id = ':'.join(
            [
                ''.join(make_id(*cls.id_component(self)))
                for cls in type_sequence
            ])

        self._data = data
        self._entity_id = entity_id
        self._entity_path = path

    @property
    def data(self) -> DataDict:
        """
        Return the data dictionary to be stored in the node.

        Returns
        -------
        Dict[str, Any]
            Dictionary passed as kwargs to ``nx.Graph().add_node``.
        """
        return self._data

    @property
    def entity_id(self) -> str:
        """
        Return unique identifier of an entity.
        """
        return self._entity_id

    @property
    def parent(self) -> 'ProjectEntity':
        """
        Return ``ProjectEntity`` instance that is parent to this.

        Returns
        -------
        ProjectNode
            The return instance would have a ParentToChild and
            ChildToParent edges with this if they were both added
            to a graph.
        """
        if self._parent is None:
            self._parent = self.init_parent()
        return self._parent

    @property
    def path(self) -> Path:
        """
        Return the path that identifies entity source file.

        Returns
        -------
        Path
            A path that uniquely identifies a file the
            entity represents or is derived from.
        """
        return self._path

    @property
    def super(self) -> 'ProjectEntity':
        """
        Return an instance of the base class.

        Returns
        -------
        ProjectEntity
            This instance super class can be initialized using
            the instance attributes. The returned ``ProjectEntity``
            is the outcome of that initialization operation.
        """
        if self._super is None:
            self._super = self.init_super()
        return self._super

    @property
    def type(self):
        """
        Return self.__class__.
        """
        return self.__class__

    @property
    def typename(self) -> str:
        """
        Return class name through property.

        Returns
        -------
        str
            The name of this instance's class
        """
        return self.type.__name__

    def init_base_class(self, base: Type['ProjectEntity']) -> 'ProjectEntity':
        """
        Return an instance of ``type(base)`` using instancevalues.

        Parameters
        ----------
        base : Type[ProjectEntity]
            A subclass of ProjectEntity

        Returns
        -------
        ProjectEntity
            An instance of ``type(base)`` whose values are obtained
            using field values of ``self``
        """
        return base.from_subclass_instance(self)

    def init_super(self) -> 'ProjectEntityBase':
        """
        Initialize the parent entity using this instance's attributes.

        Returns
        -------
        ProjectEntityBase
            The return instance would have a ParentToChild and
            ChildToParent edges with this if they were both added
            to a graph.
        """
        super_instance = None
        if issubclass(self.__base__, ProjectEntity):
            arguments = {}
            for field in fields(self.__base__):
                arguments[field.name] = getattr(self, field.name)
            super_instance = self.__base__(**arguments)
        return super_instance

    @classmethod
    def fields_from_data(cls, data: DataDict) -> Dict[str, Any]:
        """
        Extract data dictionary from project node.

        Returns
        -------
        Dict[str, Any]
            The data dictionary extracted from this instance.
        """
        result = {}
        super_cls = cls.__base__
        if issubclass(cls.__base__,
                      ProjectEntity) and cls.__base__ is not ProjectEntity:
            super_fields = {f.name for f in fields(super_cls)}
        else:
            super_fields = set()
        for field in fields(cls):
            if field.name in super_fields:
                continue
            result[field.name] = data[field.name]
        return result

    @classmethod
    def not_inherited_fields(cls) -> Set[str]:
        """
        Return list of keys expected in entity data.
        """
        if cls is not ProjectEntity:
            if cls.__base__ is not ProjectEntity:
                ignore = {f.name for f in fields(cls.__base__)}
            else:
                ignore = set()
            field_names = {f.name for f in fields(cls) if f.name not in ignore}
        else:
            field_names = set()
        return field_names

    @classmethod
    def from_instance(cls, instance: 'ProjectEntity', *args, **kwargs):
        """
        Initialize project node using given instance attributes.

        Parameters
        ----------
        instance : ProjectEntity
            A project node instance whose attributes will be
            used to populate this class's instance's attributes.
            Any missing arguments or keyword arguments must be
            provided via *args, **kwargs.

        Returns
        -------
        ProjectEntity
            A project entity initialized using values from a different
            project entity.
        """
        args = list(args)
        arguments = {}
        for field in fields(cls):
            if len(args) > 0:
                value = args.pop()
            elif field.name in kwargs:
                value = kwargs[field.name]
            elif hasattr(instance, field.name):
                value = getattr(instance, field.name)
            else:
                continue
            arguments[field.name] = value
        return cls(**arguments)

    @classmethod
    def from_parent(
            cls,
            parent_instance: 'ProjectEntity',
            *args,
            **kwargs) -> 'ProjectEntity':
        """
        Initialize project node using given instance attributes.

        Parameters
        ----------
        parent_instance : ProjectEntity
            A project entity instance that is expected
            to have a parent-like relationship with
            output instance (not neccessarily inheritance).
        """
        instance = cls.from_instance(parent_instance, *args, **kwargs)
        return instance

    @classmethod
    def from_super(
            cls,
            super_instance: 'ProjectEntity',
            *args,
            **kwargs) -> 'ProjectEntity':
        """
        Initialize instance using instance from base class.

        Parameters
        ----------
        super_instance : ProjectEntity
            A project node instance that is expected to be the
            super of the returned project entity instance.
        args: Tuple[Any]
            These values override leading field values contained
            in instance values.
        **kwargs: Dict[Any, Any]
            These values override instance values.

        Returns
        -------
        ProjectNode
            A project node that contains the super instance as
            a subset of it's attributes.
        """
        instance = cls.from_instance(super_instance, *args, **kwargs)
        return instance

    @classmethod
    def from_subclass_instance(
            cls,
            subclass_instance: 'ProjectEntity') -> 'ProjectEntity':
        """
        Return ``cls`` instance where instance is subclass of ``cls``.

        Parameters
        ----------
        graph : nx.Graph
            The graph containing the node ``node``.
        instance : ProjectEntity
            An instance of a subclass of ``cls``.

        Returns
        -------
        ProjectEntity
            An instance of ``cls`` whose values are
            are copies of ``subclass_instance`` values.

        Raises
        ------
        TypeError
            Exception raised if ``subclass_instance.__class__``
            is not a subclass of ``cls``.
        """
        if not isinstance(subclass_instance, cls):
            iname = subclass_instance.__class__.__name__
            cname = cls.__name__
            raise TypeError(
                f"Instance class ({iname}) is not a subclass of {cname}")
        return cls.from_instance(subclass_instance)

    @classmethod
    def from_subclass_get(cls, instance: 'ProjectEntity', attr: str) -> Any:
        """
        Return attribute value.

        Parameters
        ----------
        instance : ProjectEntity
            _description_
        attr : str
            _description_

        Returns
        -------
        Any
            _description_
        """
        cls.from_subclass_instance()
        pass
