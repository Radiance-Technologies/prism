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
Utilities related to Coq kernel names and qualified identifiers.
"""
from typing import List, Tuple, Union

from prism.language.sexp import SexpNode
from prism.util.opam.version import OpamVersion, Version


def interpolate_names(short_id: str, full_id: str) -> List[str]:
    """
    Interpolate between given minimally and fully qualified identifiers.

    Parameters
    ----------
    short_id : str
        The minimally qualified version of the identifier in some
        context.
    full_id : str
        The fully qualified version of the identifier.

    Returns
    -------
    List[str]
        A sequence of equivalent identifiers from minimally to fully
        qualified.
    """
    if not full_id.endswith(short_id):
        raise ValueError(
            f"The given identifiers are not related: {short_id}, {full_id}")
    qualid = short_id
    qualids = [qualid]
    for component in reversed(full_id[:-(len(short_id) + 1)].split(".")):
        qualid = '.'.join([component, qualid])
        qualids.append(qualid)
    return qualids


def print_dir_path(dir_path: SexpNode) -> str:
    """
    Pretty-print a serialized ``DirPath`` data type.

    Parameters
    ----------
    dir_path : SexpNode
        An s-expression denoting some logical library path.

    Returns
    -------
    str
        The period-delimited name of the library.

    Notes
    -----
    ``DirPath`` is a seemingly stable data type defined in
    ``coq/kernel/names.ml``.
    """
    return ".".join([str(x[1]) for x in dir_path[1]][::-1])


def print_mod_path(mod_path: SexpNode) -> str:
    """
    Pretty print a serialized ``ModPath`` data type.

    Parameters
    ----------
    mod_path : SexpNode
        An s-expression denoting the path to some defined entity.

    Returns
    -------
    str
        The kernel name of the given entity.

    Notes
    -----
    ``ModPath`` is a seemingly stable data type defined in
    ``coq/kernel/names.ml``.
    """
    if mod_path[0].get_content() == "MPdot":
        label_id = mod_path[2][1]
        mod_path = mod_path[1]
        return print_mod_path(mod_path) + "." + str(label_id)
    elif mod_path[0].get_content() == "MPfile":
        return print_dir_path(mod_path[1])
    else:
        assert mod_path[0].get_content() == "MPbound"
        mb_id = mod_path[1]
        mb_id_id = mb_id[1][1]
        return ".".join(print_dir_path(mb_id[2]) + [str(mb_id_id)])


def print_ker_name(
        ker_name: SexpNode,
        serapi_version: Version,
        return_modpath: bool = True) -> Union[str,
                                              Tuple[str,
                                                    SexpNode]]:
    """
    Pretty print a serialized ``KerName`` data type.

    Parameters
    ----------
    ker_name : SexpNode
        An s-expression denoting a Coq kernel name.
    serapi_version : Version
        The version of SerAPI to be compared against Coq versions for
        interpretation of the correct serialization.
    return_modpath : bool, optional
        Whether to return the s-expression node for the ``modpath``
        attribute of the ``KerName`` data structure, by default True.

    Returns
    -------
    str
        The pretty-printed qualified identifier corresponding to the
        given kernel name.
    modpath : SexpNode, optional
        The ``modpath`` attribute is also returned if `return_modpath`
        is True.

    Notes
    -----
    ``KerName`` is an unstable data type defined in
    ``coq/kernel/names.ml`` that manifests as the ``Constant`` and
    ``MutInd`` types.
    """
    # follow coq/kernel/names.ml::KerName.to_string_gen as guide
    if OpamVersion.less_than(serapi_version, '8.9.0'):
        modpath = ker_name[2]
        dirpath = ker_name[3]
        knlabel = ker_name[4]
    elif OpamVersion.less_than(serapi_version, '8.10.0'):
        # canary field removed
        modpath = ker_name[1]
        dirpath = ker_name[2]
        knlabel = ker_name[3]
    else:
        # dirpath field removed
        modpath = ker_name[1]
        dirpath = None
        knlabel = ker_name[2]
    if dirpath is not None:
        dirpath = print_dir_path(dirpath)
    qualid = f"#{dirpath}#" if dirpath else "."
    qualid = print_mod_path(modpath) + qualid + str(knlabel[1])
    if return_modpath:
        return qualid, modpath
    else:
        return qualid


def mod_path_file(mod_path: SexpNode) -> str:
    """
    Get the logical filename, if any, from a ``ModPath`` data type.

    Parameters
    ----------
    modpath : SexpNode
        An s-expression denoting the path to some defined entity.

    Returns
    -------
    str
        The period-delimited name of the library containing the given
        entity.
    """
    if mod_path[0].get_content() == "MPdot":
        return mod_path_file(mod_path[1])
    elif mod_path[0].get_content() == "MPfile":
        return print_dir_path(mod_path[1])
    else:
        assert mod_path[0].get_content() == "MPbound"
        mb_id = mod_path[1]
        return print_dir_path(mb_id[2])
