"""
Supply a protocol for serializable data.
"""

import os
import typing
from dataclasses import dataclass, fields, is_dataclass
from typing import (
    Any,
    Dict,
    Generic,
    Optional,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

import seutil as su
import typing_inspect
import yaml
from diff_match_patch import diff_match_patch

from prism.util.radpytools.dataclasses import Dataclass

_dmp = diff_match_patch()
# Produce smaller diffs
_dmp.Patch_Margin = 1


@runtime_checkable
class Serializable(Protocol):
    """
    A simple protocol for serializable data.
    """

    def dump(
            self,
            output_filepath: os.PathLike,
            fmt: su.io.Fmt = su.io.Fmt.yaml) -> None:
        """
        Serialize data to text file.

        Parameters
        ----------
        output_filepath : os.PathLike
            Filepath to which cache should be dumped.
        fmt : su.io.Fmt, optional
            Designated format of the output file,
            by default `su.io.Fmt.yaml`.
        """
        su.io.dump(output_filepath, self, fmt=fmt)

    @classmethod
    def load(
            cls,
            filepath: os.PathLike,
            fmt: Optional[su.io.Fmt] = None) -> 'Serializable':
        """
        Load a serialized object from file..

        Parameters
        ----------
        filepath : os.PathLike
            Filepath containing repair mining cache.
        fmt : Optional[su.io.Fmt], optional
            Designated format of the input file, by default None.
            If None, then the format is inferred from the extension.

        Returns
        -------
        Serializable
            The deserialized object.
        """
        return su.io.load(filepath, fmt, clz=cls)


_S = TypeVar('_S')


@dataclass
class SerializableDataDiff(Generic[_S]):
    """
    A diff between two serializable objects.
    """

    diff: str

    def patch(self, a: _S) -> _S:
        """
        Apply the diff to a given object to obtain a changed one.

        Parameters
        ----------
        a : object
            An object that can be serialized and deserialized.

        Returns
        -------
        object
            The object resulting from applying this diff to `a`.
            If there exists some `b` such that `self` equals
            ``SerializableDiff.compute_diff(a,b)``, then
            ``self.patch(a) == b``.
        """
        clz = type(a)
        a = su.io.serialize(a, fmt=su.io.Fmt.yaml)
        a_str = typing.cast(str, yaml.safe_dump(a))
        patches = _dmp.patch_fromText(self.diff)
        patched_a_str, _ = _dmp.patch_apply(patches, a_str)
        patched_a = yaml.safe_load(patched_a_str)
        patched_a = su.io.deserialize(patched_a, clz=clz, error="raise")
        return patched_a

    @classmethod
    def compute_diff(cls, a: _S, b: _S) -> 'SerializableDataDiff':
        """
        Get a diff between two serializable objects of the same type.

        Parameters
        ----------
        a, b : object
            Objects that can be serialized.

        Returns
        -------
        SerializableDiff
            A text representation of the diff between `a` and `b`.
        """
        fmt = su.io.Fmt.yaml
        a = su.io.serialize(a, fmt=fmt)
        b = su.io.serialize(b, fmt=fmt)
        a_str = typing.cast(str, yaml.safe_dump(a))
        b_str = typing.cast(str, yaml.safe_dump(b))
        patches = _dmp.patch_make(a_str, b_str)
        diff = _dmp.patch_toText(patches)
        return SerializableDataDiff(diff)


_Generic = Any
"""
Surrogate alias for Generic types.

Limitation of available type hints pre-Python 3.10.
"""


def get_typevar_bindings(
        clz) -> Tuple[Union[type,
                            _Generic,
                            Tuple],
                      Dict[TypeVar,
                           type]]:
    """
    Get the type variable bindings for a given class.

    This includes any implicitly bound type variables in base classes.

    Parameters
    ----------
    clz
        A type or generic type alias.

    Returns
    -------
    clz_origin : type
        The unapplied base type.
    Dict[TypeVar, type]
        A map from type variables to their bound types, which may be
        type variables themselves.
    """
    type_bindings: Dict[TypeVar,
                        type] = {}
    clz_origin = typing_inspect.get_origin(clz)
    if clz_origin is None:
        clz_origin = clz
    generic_bases = typing_inspect.get_generic_bases(clz_origin)
    if clz_origin is None and not generic_bases:
        # not generic
        return clz_origin, type_bindings
    clz_args = typing_inspect.get_args(clz)
    type_bindings.update({v: v for v in clz_args if isinstance(v,
                                                               TypeVar)})
    clz_args = list(reversed(clz_args))
    # bind type arguments
    for base in generic_bases:
        _, base_bindings = get_typevar_bindings(base)
        type_bindings.update(
            {
                k:
                    v if not isinstance(v,
                                        TypeVar) or not clz_args else
                    clz_args.pop() for k,
                v in base_bindings.items()
            })
    return clz_origin, type_bindings


def substitute_typevars(
        clz: Union[type,
                   _Generic,
                   Tuple],
        bindings: Dict[TypeVar,
                       type]) -> Union[type,
                                       _Generic,
                                       Tuple]:
    """
    Substitute type variables in a given type signature.

    Parameters
    ----------
    clz : Union[type, _Generic, Tuple]
        A type signature.
    bindings : Dict[TypeVar, type]
        Type variable bindings.

    Returns
    -------
    Union[type, _Generic, Tuple]
        The given type signature with type variables subsituted with
        their bound types.
    """
    f_type = typing_inspect.get_origin(clz)
    if f_type is None:
        f_type = bindings.get(clz, clz)  # type: ignore
    else:
        # bind type vars
        try:
            getitem = f_type.__class_getitem__
        except AttributeError:
            getitem = f_type.__getitem__
        f_type = getitem(
            tuple(
                substitute_typevars(tp,
                                    bindings)
                if not isinstance(tp,
                                  TypeVar) else bindings[tp]
                for tp in typing_inspect.get_args(clz)))
    return f_type


_T = TypeVar("_T", bound=Dataclass)


def _deserialize_other(data: object, clz: type, error: str):
    if typing_inspect.is_optional_type(clz):
        clz_args = typing_inspect.get_args(clz)
        if data is None:
            return None
        inner_clz = clz_args[0]
        try:
            return deserialize_generic_dataclass(data, inner_clz, error=error)
        except su.io.DeserializationError as e:
            raise su.io.DeserializationError(
                data,
                clz,
                "(Optional removed) " + e.reason)
    if typing_inspect.is_union_type(clz):
        clz_args = typing_inspect.get_args(clz)
        ret = None
        for inner_clz in clz_args:
            try:
                ret = deserialize_generic_dataclass(
                    data,
                    inner_clz,
                    error="raise")
            except su.io.DeserializationError:
                continue

        if ret is None:
            return su.io.deserialize(data, clz, error)
        else:
            return ret
    return su.io.deserialize(data, clz, error)


def deserialize_generic_dataclass(
        data: object,
        clz: Type[_T],
        error: str = "ignore") -> _T:
    """
    Deserialize a generic dataclass.

    Especially useful for dataclasses containing inherited or
    uninherited fields annotated with type variables

    Parameters
    ----------
    data : object
        Serialized data, expected to be a dictionary.
    clz : Type[Dataclass]
        A monomorphic type of dataclass that should be deserialized from
        the `data`.
    error : str, optional
        Whether to raise or ignore deserialization errors.
        One of "raise" or "ignore", by default "ignore".

    Returns
    -------
    Dataclass
        An instance of `clz` deserialized from the `data`.

    Raises
    ------
    su.io.DeserializationError
        If the given type is polymorphic or the `clz` is a dataclass but
        `data` is not a dictionary.
    """
    # TODO (AG): Submit as PR to seutil
    clz_origin, bindings = get_typevar_bindings(clz)
    if not bindings or not is_dataclass(clz_origin):
        # not generic
        _deserialize_other(data, clz, error)
    clz_origin = typing.cast(type, clz_origin)
    for binding in bindings.values():
        if isinstance(binding, TypeVar):
            raise su.io.DeserializationError(
                data,
                clz,
                "Cannot deserialize polymorphic type")
    if not isinstance(data, dict):
        raise su.io.DeserializationError(
            data,
            clz,
            "Expected dict serialization for dataclass")
    # deserialize the data field by field
    init_field_values: Dict[str,
                            Any] = {}
    non_init_field_values: Dict[str,
                                Any] = {}
    for f in fields(clz_origin):
        if f.name in data:
            field_values = init_field_values if f.init else non_init_field_values
            f_type = substitute_typevars(f.type, bindings)
            field_values[f.name] = deserialize_generic_dataclass(
                data.get(f.name),
                f_type,
                error=error)
    try:
        obj = clz_origin(**init_field_values)
    except TypeError as e:
        raise su.io.DeserializationError(
            data,
            clz,
            "Failed to get fields") from e
    for f_name, f_value in non_init_field_values.items():
        # use object.__setattr__ in case clz is frozen
        object.__setattr__(obj, f_name, f_value)
    return obj
