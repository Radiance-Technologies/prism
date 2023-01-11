"""
Module for tool to help run commands get resource usage.
"""
import re
from math import ceil
from subprocess import CompletedProcess
from typing import Dict, Optional, Tuple

from seutil import bash

from prism.tests import _MEMORY_SCRIPT_PATH, _TIMEOUT_SCRIPT_PATH


class ResourceTestTool:
    """
    Helper tool to run bash commands to test resource usage.
    """

    COMMAND_MEMORY: str = f"python {_MEMORY_SCRIPT_PATH}"
    """
    Script that allocates byte array. First argument is
    size of the array.
    """

    COMMAND_RUNTIME: str = f"python {_TIMEOUT_SCRIPT_PATH}"
    """
    Script that sleeps and sends signal.SIGXCPU if runtime
    limit is expired.
    """

    PREFIX: str = (
        "/usr/bin/time -f"
        "'Elapsed time: %es\\n"
        "Memory usage: %M KB\\n"
        "CPU usage: %P'")
    """
    A shell command that returns memory, runtime,
    and cpu usage information of commands that follow
    it. Should be prepended and executed with a command.
    """

    RE_MEMORY_USAGE: str = r'Memory usage: \d+.*'
    """
    REGEX pattern to extract memory from output of `PREFIX`.
    """

    RE_RUNTIME_USAGE: str = r'Elapsed time: \d+.*'
    """
    REGEX pattern to extract runtime from output of `PREFIX`.
    """

    MEMORY_KEY: str = "MEMORY"
    """
    Key used get memory usage from parsed output of `PREFIX` command.
    """

    RUNTIME_KEY: str = "RUNTIME"
    """
    Key used get runtime from parsed output of `PREFIX` command.
    """

    @classmethod
    def _make_command(cls, cmd: str, amt: int) -> str:
        """
        Create resource testing command.

        Parameters
        ----------
        cmd : str
            Bash command that will be monitored
            for resource usage.
        amt : int
            Argument to resource testing script.

        Returns
        -------
        str
            Command that runs and returns resource
            usage to STDERR.
        """
        return f"{cls.PREFIX} {cmd} {amt}"

    @classmethod
    def _command_memory(cls, amt: int) -> str:
        """
        Return command to allocate bytearray with `amt` bytes.

        This will consume more memory for larger values.

        Parameters
        ----------
        amt : int
            Number of bytes to allocate in command.
            This does not equal to memory usage running the command.

        Returns
        -------
        str
            Command to allocate `amt` bytes of memory within a
            process.
        """
        return cls._make_command(cls.COMMAND_MEMORY, amt)

    @classmethod
    def _command_runtime(cls, amt: int) -> str:
        """
        Run sleep command for `amt` seconds.

        Parameters
        ----------
        amt : int
            Number of seconds to sleep.

        Returns
        -------
        str
            Command to sleep in process for `amt`
            seconds.
        """
        return cls._make_command(cls.COMMAND_RUNTIME, amt)

    @classmethod
    def _parse_resource_usage(cls, text: str) -> Dict[str, Optional[int]]:
        """
        Extract resource used values from text.

        Parameters
        ----------
        text : str
            The standard error output of a
            ``subprocess.CompletedProcess`` run with
            `cls.PREFIX`.


        Returns
        -------
        Dict[str, Optional[int]]
            Mapping of resource usage to resource names
            extracted from `text`. If a value is None,
            then the resource amount was not found in
            the text.
        """
        mapping = {
            cls.MEMORY_KEY: cls.RE_MEMORY_USAGE,
            cls.RUNTIME_KEY: cls.RE_RUNTIME_USAGE,
        }
        scaling = {
            cls.MEMORY_KEY: 1000,
            cls.RUNTIME_KEY: 1,
        }
        usage = {}
        for name, pattern in mapping.items():
            try:
                subtext = re.findall(pattern, text)[0]
                subpattern = r'\d+\.\d+' if '.' in subtext else r'\d+'
                value = re.findall(subpattern, subtext)[0]
                usage[name] = int(ceil(float(value))) * scaling[name]
            except Exception:
                usage[name] = None
        return usage

    @classmethod
    def run_cmd(
        cls,
        cmd: str,
        **kwargs,
    ) -> Tuple[CompletedProcess,
               Dict[str,
                    int]]:
        """
        Run `cmd` and parse resource usage from output.

        Parameters
        ----------
        cmd : str
            A bash command.

        Returns
        -------
        CompletedProcess
            The completed process object returned by
            subprocess.
        Dict[str, Optional[int]]
            The resource usage from running the command.
        """
        output = bash.run(cmd, **kwargs)
        usage = cls._parse_resource_usage(output.stderr)
        return output, usage

    @classmethod
    def run_memory_cmd(
        cls,
        amt: int,
        **kwargs,
    ) -> Tuple[CompletedProcess,
               Dict[str,
                    Optional[int]]]:
        """
        Run command to allocate bytearray with `amt` bytes.

        Parameters
        ----------
        amt : int
            Number of bytes to allocate in command.
            This does not equal to memory usage running the command.

        Returns
        -------
        CompletedProcess
            The completed process object returned by
            subprocess.
        Dict[str, Optional[int]]
            The resource usage from running the command.
        """
        return cls.run_cmd(cls._command_memory(amt), **kwargs)

    @classmethod
    def run_runtime_cmd(
        cls,
        amt: int,
        **kwargs,
    ) -> Tuple[CompletedProcess,
               Dict[str,
                    Optional[int]]]:
        """
        Run sleep command for `amt` seconds.

        Parameters
        ----------
        amt : int
            Number of seconds to sleep.

        Returns
        -------
        CompletedProcess
            The completed process object returned by
            subprocess.
        Dict[str, Optional[int]]
            The resource usage from running the command.
        """
        return cls.run_cmd(cls._command_runtime(amt), **kwargs)
