"""
coqgym_interface: Utilities for interacting with CoqGym.
"""

from setuptools import setup

setup(
    use_scm_version={
        "root": "..",
        "relative_to": __file__
    },
    setup_requires=['setuptools_scm'])
