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
Synchronization helpers for multiprocessing.
"""

import typing
from multiprocessing import RLock
from multiprocessing.synchronize import SemLock
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union

from prism.util.radpytools import Descriptor, _NonDataDescriptor, descriptor

_S = TypeVar('_S')
_T = TypeVar('_T')


def critical(
    f: Optional[Callable[...,
                         _S]] = None,
    lock: Optional[SemLock] = None
) -> Union[Callable[[Callable[...,
                              _S]],
                    Callable[...,
                             _S]],
           Callable[...,
                    _S]]:
    """
    Wrap a function in a semaphore/lock for thread-safe synchronization.

    Parameters
    ----------
    f : Callable[[T], S], optional
        An arbitrary function.
        If not provided, then a partially applied wrapper is returned
        that will synchronize a given function with the given lock.
    lock : Optional[SemLock], optional
        A semaphore or lock with which to synchronize `f`.
        By default, a reentrant lock (`RLock`) is used.

    Returns
    -------
    callable
        Either the given function `f` wrapped with a semaphore/lock or a
        higher-order function that will synchronize given functions
        with respect to the given lock.
    """
    if lock is None:
        lock = RLock()

    def inner(f):

        def g(*args, **kwargs):
            with lock:
                return f(*args, **kwargs)

        return g

    if f is not None:
        return inner(f)

    # no args passed, must have been
    # keyword configuration.

    return inner


class _synchronizedmethod(descriptor[_T]):
    """
    Internal implementation of synchronized methods.

    See Also
    --------
    synchronizedmethod: For public API.
    """

    semlock_lock = RLock()
    """
    Synchronization lock for setting semlock attributes on instances
    since semlocks may be shared between methods.
    """

    # NOTE (AG): It looks like I chose a poor example to emulate caching
    # when basing this on functools.cached_property. Track the
    # resolution of https://github.com/python/cpython/issues/87634.

    def __init__(
            self,
            func: Callable[...,
                           Any],
            *,
            semlock_name: Optional[str] = None,
            semlock_cls: Callable[...,
                                  SemLock] = RLock,
            **kwargs: Dict[str,
                           Any]) -> None:
        super().__init__(func, require_read=True)
        self.semlock_name = semlock_name
        self.sync_name: str
        self.lock = RLock()
        self._semlock_cls = semlock_cls
        self._semlock_kwargs = kwargs

    def __set_name__(self, owner: Type[_T], name: str) -> None:
        """
        Set the name of the descriptor and synchronization wrapper.

        Parameters
        ----------
        owner : Type[T]
            The class defining the synchronized method.
        name : str
            The name of the attribute to which this descriptor is
            assigned.

        Raises
        ------
        TypeError
            If one attempts to alter the name of the descriptor.
        """
        super().__set_name__(owner, name)
        if self.semlock_name is None:
            self.semlock_name = self.get_semlock_name(name, owner)
        self.sync_name = self.get_sync_name(name, owner)

    def __get__(self,  # noqa: C901
                instance: _T,
                owner: Optional[Type[_T]] = None) -> Any:
        """
        Retrieve the synchronized method wrapper.

        Each instance of the class is assigned its own lock.

        Parameters
        ----------
        instance : T
            An instance of the synchronized method owner.
        owner : type, optional
            The type of the instance, by default None.

        Returns
        -------
        callable
            The instance method wrapped with a synchronization
            mechanism.

        Notes
        -----
        On first invocation on a given `instance`, a wrapper for the
        instance's method that manages the synchronization is created
        and assigned to the attribute ``self.sync_name``.
        """
        if instance is None and owner is None:
            return self
        obj: Union[_T, Optional[Type[_T]]]
        if self._isclassmethod:
            obj = owner
        else:
            obj = instance
        if owner is None:
            assert instance is not None
            owner = type(instance)
        if obj is not None:
            try:
                result = getattr(obj, self.sync_name)
            except AttributeError:
                with self.lock:
                    # check to see if another thread created the wrapper
                    # while we waited for this lock
                    try:
                        result = getattr(obj, self.sync_name)
                    except AttributeError:
                        assert self.semlock_name is not None
                        # Create the synchronization wrapper.
                        # Get semlock used for synchronization
                        try:
                            semlock = getattr(obj, self.semlock_name)
                        except AttributeError:
                            with self.semlock_lock:
                                # check to see if another thread created
                                # the semlock while we waited for this
                                # lock
                                try:
                                    semlock = getattr(obj, self.semlock_name)
                                except AttributeError:
                                    # create and store semlock
                                    semlock = self._semlock_cls(
                                        **self._semlock_kwargs)
                                    if self._isclassmethod:
                                        assert isinstance(obj, type)
                                        type.__setattr__(
                                            obj,
                                            self.semlock_name,
                                            semlock)
                                    else:
                                        object.__setattr__(
                                            obj,
                                            self.semlock_name,
                                            semlock)
                        if not isinstance(semlock, SemLock):
                            raise TypeError(
                                f"{self.semlock_name} is not a supported"
                                f"synchronization primitive (got {semlock!r})")

                        assert isinstance(self._f, _NonDataDescriptor)
                        # create and store synchronization wrapper
                        if self._isproperty:
                            wrapper: Callable[
                                [],
                                Any] = typing.cast(
                                    Callable[[],
                                             Any],
                                    critical(
                                        lambda: typing.cast(
                                            _NonDataDescriptor,
                                            self._f).__get__(instance,
                                                             owner),
                                        semlock))
                        else:
                            wrapper = typing.cast(
                                Callable[[],
                                         Any],
                                critical(
                                    self._f.__get__(instance,
                                                    owner),
                                    semlock))
                        if self._isclassmethod:
                            assert isinstance(obj, type)
                            type.__setattr__(obj, self.sync_name, wrapper)
                        else:
                            object.__setattr__(obj, self.sync_name, wrapper)
                        result = wrapper
            if self._isproperty:
                result = result()
            return result
        else:
            # obj can only be None if a class tried to call an instance
            # method
            assert isinstance(self._f, _NonDataDescriptor)
            return self._f.__get__(instance, owner)

    def __set__(self, _instance: _T, _value: Any) -> None:
        """
        Reject attempts to overwrite the method.
        """
        raise AttributeError(f"Cannot set synchronized method {self._f_name}")

    @staticmethod
    def get_semlock_name(method_name: str, owner: Type[_T]) -> str:
        """
        Return the canonical name of a method's semaphore/lock.

        Parameters
        ----------
        method_name : str
            The name of a method.
        owner : type
            The class that owns the method.

        Returns
        -------
        str
            The name of the corresponding lock.
        """
        return f'_{method_name}_{owner.__module__}_{owner.__name__}_semlock'

    @staticmethod
    def get_sync_name(method_name: str, owner: Type[_T]) -> str:
        """
        Return the canonical name of a method's synchronization wrapper.

        Parameters
        ----------
        method_name : str
            The name of a method.
        owner : type
            The class that owns the method.

        Returns
        -------
        str
            The name of the corresponding synchronization wrapper.
        """
        return f'_{method_name}_{owner.__module__}_{owner.__name__}_sync'


# once yapf and other tools support positional-only parameters, alter
# the definition to ``def synchronizedmethod(f, /, *, ...)``
def synchronizedmethod(
    _func: Optional[Union[Callable[...,
                                   Any],
                          Descriptor]] = None,
    *,
    semlock_name: Optional[str] = None,
    semlock_cls: Callable[...,
                          SemLock] = RLock,
    **kwargs: Dict[str,
                   Any]
) -> Union[_synchronizedmethod[_T],
           Callable[[Callable[...,
                              Any]],
                    _synchronizedmethod[_T]]]:
    """
    Make a synchronized method decorator.

    A wrapper around a method that synchronizes its execution with a
    semaphore/lock.
    The lock may be created on a per-method basis (the default) or
    grouped with other methods according to a provided name.

    Parameters
    ----------
    _func : callable
        The method to be wrapped with a caching mechanism.
        The arguments to `f` must be hashable.
        This argument should not be called by keyword and must be
        provided positionally.
    semlock_name : str or None, optional
        The name of the semaphore/lock, by default None.
        If None, then a name unique to the synchronized method is
        generated.
        If it does not already exist, an attribute with the name will be
        created to store the synchronization primitive.
        Thus, one may synchronize with an attribute that already exists
        as an attribute in the class or instance, for example.
    semlock_cls : Callable[..., SemLock], optional
        Nominally, the type of synchronization primitive to associate
        with `semlock_name`.
        In practice, a function that takes an argument and returns an
        instance of `SemLock`.
        By default, `RLock` is assumed.
    kwargs
        Additional keyword arguments to `semlock_cls` (e.g., the
        initial value for a semaphore).

    Returns
    -------
    _synchronizedmethod
        Internal implementation of a synchronized method.

    Examples
    --------
    >>> class Example:
    ...     xs : List[int] = []
    ...
    ...     @synchronizedmethod
    ...     def f(self, ys : Iterable[int]) -> None:
    ...         for y in ys:
    ...             self.xs.append(y)
    ...
    >>> ex = Example()
    >>> tasks = [range(5), range(5)]
    >>> with multiprocessing.pool.ThreadPool(2) as pool:
    ...     pool.map(ex.f, tasks)
    [None, None]
    >>> ex.xs
    [0, 1, 2, 3, 4, 0, 1, 2, 3, 4]
    """

    def wrap(func):
        return _synchronizedmethod(
            func,
            semlock_name=semlock_name,
            semlock_cls=semlock_cls,
            **kwargs)

    # See if we're called as @synchronizedmethod or
    # @synchronizedmethod()
    if _func is None:
        # called as @synchronizedmethod()
        return wrap

    # called without parentheses
    return wrap(_func)


def synchronizedproperty(
    _func: Optional[Callable[...,
                             Any]] = None,
    *,
    semlock_name: Optional[str] = None,
    semlock_cls: Callable[...,
                          SemLock] = RLock,
    **kwargs: Dict[str,
                   Any]
) -> Union[_synchronizedmethod,
           Callable[[Callable[...,
                              Any]],
                    _synchronizedmethod]]:
    """
    Make a synchronized property decorator.

    A wrapper around a method that synchronizes its execution with a
    semaphore/lock and behaves outwardly as a property.
    The lock may be created on a per-method basis (the default) or
    grouped with other methods according to a provided name.

    Parameters
    ----------
    _func : callable
        The method to be wrapped with a caching mechanism.
        The arguments to `f` must be hashable.
        This argument should not be called by keyword and must be
        provided positionally.
    semlock_name : str or None, optional
        The name of the semaphore/lock, by default None.
        If None, then a name unique to the synchronized method is
        generated.
        If it does not already exist, an attribute with the name will be
        created to store the synchronization primitive.
        Thus, one may synchronize with an attribute that already exists
        as an attribute in the class or instance, for example.
    semlock_cls : Callable[..., SemLock], optional
        Nominally, the type of synchronization primitive to associate
        with `semlock_name`.
        In practice, a function that takes an argument and returns an
        instance of `SemLock`.
        By default, `RLock` is assumed.
    kwargs
        Additional keyword arguments to `semlock_cls` (e.g., the
        initial value for a semaphore).

    Returns
    -------
    _synchronizedmethod
        Internal implementation of a synchronized method.

    Examples
    --------
    >>> class Example:
    ...     xs : List[int] = []
    ...
    ...     @synchronizedproperty
    ...     def f(self) -> List[int]:
    ...         for y in range(5):
    ...             self.xs.append(y)
    ...         return list(self.xs)
    ...
    >>> ex = Example()
    >>> tasks = [(), ()]
    >>> with multiprocessing.pool.ThreadPool(2) as pool:
    ...     pool.map(ex.f, tasks)
    [[0, 1, 2, 3, 4], [0, 1, 2, 3, 4, 0, 1, 2, 3, 4]]
    """

    def wrap(func: Callable[..., Any]) -> _synchronizedmethod:
        return typing.cast(
            _synchronizedmethod,
            synchronizedmethod(
                property(func),
                semlock_name=semlock_name,
                semlock_cls=semlock_cls,
                **kwargs))

    # See if we're called as @synchronizedproperty or
    # @synchronizedmethod()
    if _func is None:
        # called as @synchronizedproperty()
        return wrap

    # called without parentheses
    return wrap(_func)
