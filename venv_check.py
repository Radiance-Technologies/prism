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
