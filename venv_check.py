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
Check if the user is currently executing in a virtual environment.
"""
import os
import sys


def is_external_venv():
    """
    Return if we are in a virtualenv virtual environment.

    Returns False if the virtual environment points to the Python not
    created by `setup_python.sh`.
    """
    return (
        hasattr(sys,
                'real_prefix')
        or (hasattr(sys,
                    'base_prefix') and sys.base_prefix != sys.prefix))


def is_internal_venv():
    """
    Return if we are in a virtualenv virtual environment.

    Returns True if the virtual environment points to the Python
    created by `setup_python.sh`.

    Note: This may fail if the environment variable is set but
    the user is not actually in an active virtual environment.
    This edge case may occur if the script is executing within a
    shell spawned from within the virtual environment, for
    example.
    """
    try:
        os.environ['VIRTUAL_ENV']
        return not is_external_venv()
    except KeyError:
        return False


def is_conda_venv():
    """
    Return if we are in a Conda virtual environment.
    """
    return "CONDA_DEFAULT_ENV" in os.environ


def is_venv():
    """
    Return if we are in a virtualenv virtual environment.
    """
    return is_external_venv() or is_internal_venv()


if __name__ == "__main__":
    if not is_conda_venv():
        print(is_venv())
    else:
        print('CONDA')
