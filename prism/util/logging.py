"""
Utilities for logging.
"""
import logging
import typing
from multiprocessing.managers import BaseManager
from typing import Generic, NoReturn, Type, TypeVar

from prism.util.debug import Debug
from prism.util.exceptions import Except


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


class SpecialLogger:
    """
    Logger for writing logs during multiprocessing.
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def __getattr__(self, name: str):
        """
        Check logger for missing attributes.
        """
        return getattr(self.logger, name)

    def get_logger(self) -> logging.Logger:
        """
        Return the logger type used by manager.
        """
        return self.logger

    def write_exception_log(self, exception: Except[None]):
        """
        Write a log entry for the given exception.

        logging.Logger objects are not multi-processing-safe, so this
        method is synchronized to prevent simultaneous write attempts.

        Parameters
        ----------
        exception : Except[None]
            Exception to write a log entry for
        """
        self.logger.exception(exception.exception)
        self.logger.error(f"Traceback: {exception.trace}")

    def write_debug_log(self, message: str):
        """
        Write a debug message.

        Parameters
        ----------
        message : str
            Message to write as a debug message to the logger.
        """
        self.logger.debug(message)


L = TypeVar('L', bound=SpecialLogger)


class SpecialLoggerServer(BaseManager, Generic[L]):
    """
    A BaseManager-derived server for managing logs.

    Logger should not be used directly, but instead it should be
    subclassed.
    """

    def __new__(cls, *args, **kwargs):
        """
        Register logger with base manager.
        """
        logger_type = cls.get_logger_type()
        cls.register(logger_type.__name__, logger_type)
        return super().__new__(cls, *args, **kwargs)

    @property
    def getClient(self) -> Type[L]:
        """
        Return client class in style of a factory.
        """
        logger_type = self.get_logger_type()
        return getattr(self, logger_type.__name__)

    @classmethod
    def get_logger_type(cls) -> Type[L]:
        """
        Return the logger type used by manager.
        """
        return typing.get_args(cls.__orig_bases__[0])[0]  # type: ignore
