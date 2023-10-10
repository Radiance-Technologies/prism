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
Utilities for logging.
"""
import logging
from typing import NoReturn, Type

from prism.util.debug import Debug


def default_log_level() -> int:
    """
    Get the default log level based on debugging status.
    """
    return logging.DEBUG if Debug.is_debug else logging.INFO


def log_and_raise(
        logger: logging.Logger,
        msg: str,
        error: Type[Exception]) -> NoReturn:
    """
    Log an error message and then raise it as part of an exception.

    Parameters
    ----------
    logger : logging.Logger
        The logger.
    msg : str
        The error message.
    error : Type[Exception]
        The type of error.

    Raises
    ------
    Exception
        The given exception class.
    """
    logger.log(msg)
    raise error(msg)
