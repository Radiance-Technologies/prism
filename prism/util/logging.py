"""
Utilities for logging.
"""
import logging
import typing
from copy import deepcopy
from multiprocessing.managers import BaseManager
from typing import Generic, NoReturn, Optional, Type, TypeVar, Union

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


class ManagedClient:
    """
    Logger for writing logs during multiprocessing.
    """

    def __init__(
        self,
        logger: Optional[Union[str,
                               Union[logging.Logger,
                                     'ManagedClient']]] = __name__):

        if isinstance(logger, ManagedClient):
            logger = logger.logger
        if logger is not None:
            self.logger = self.init_logger(logger)
        else:
            self.logger = None

    def init_logger(self, logger: Union[str, logging.Logger], *args, **kwargs):
        """
        Initialize logger.
        """
        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        return logger

    def info(self, *args, **kwargs):
        """
        Create info log message.
        """
        assert self.logger is not None
        self.logger.info(*args, **kwargs)

    def warn(self, *args, **kwargs):
        """
        Create warn log message.
        """
        assert self.logger is not None
        self.logger.warn(*args, **kwargs)

    def exception(self, *args, **kwargs):
        """
        Create exception log message.
        """
        assert self.logger is not None
        self.logger.exception(*args, **kwargs)

    def debug(self, *args, **kwargs):
        """
        Create debug log message.
        """
        assert self.logger is not None
        self.logger.debug(*args, **kwargs)

    def critical(self, *args, **kwargs):
        """
        Create critical log message.
        """
        assert self.logger is not None
        self.logger.critical(*args, **kwargs)

    def getChild(self, name: str, *args, **kwargs) -> 'ManagedClient':
        """
        Create a child client.
        """
        assert self.logger is not None
        child = self.logger.getChild(name)
        client = deepcopy(self)
        client.init_logger(child, *args, **kwargs)
        return client

    def getLogger(self, name: str, *args, **kwargs) -> 'ManagedClient':
        """
        Create a client with a logger that has the given name.
        """
        assert self.logger is not None
        logger = logging.getLogger(name)
        client = deepcopy(self)
        client.init_logger(logger, *args, **kwargs)
        return client


ManagedLoggerType = TypeVar('ManagedLoggerType', bound=ManagedClient)


class ManagedServer(BaseManager, Generic[ManagedLoggerType]):
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
    def getClient(self) -> Type[ManagedLoggerType]:
        """
        Return client class in style of a factory.
        """
        logger_type = self.get_logger_type()
        return getattr(self, logger_type.__name__)

    @classmethod
    def get_logger_type(cls) -> Type[ManagedLoggerType]:
        """
        Return the logger type used by manager.
        """
        return typing.get_args(cls.__orig_bases__[0])[0]  # type: ignore
