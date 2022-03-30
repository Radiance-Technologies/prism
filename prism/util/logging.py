"""
Utilities for logging.
"""
import logging
from typing import NoReturn, Type


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
