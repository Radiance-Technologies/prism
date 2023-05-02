"""
Miscellaneous Bash-related utilities.
"""

import prism.util.string as S


def escape(cmd: str) -> str:
    """
    Sanitize the given Bash command by escaping special characters.

    Parameters
    ----------
    cmd : str
        A command intended as an argument in a Bash script or command.

    Returns
    -------
    str
        The sanitized command.
    """
    return S.escape(cmd)  # .replace("'", r"'\''")
