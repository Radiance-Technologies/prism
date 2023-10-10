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
coq-pearls: Tools for working with Coq projects and repair datasets.
"""

from pathlib import Path

from setuptools import Extension, setup

_DEBUG = False
_DEBUG_LEVEL = 0
extra_compile_args = ["-Wall", "-Wextra"]
py_limited_api = True
if _DEBUG:
    extra_compile_args += ["-g3", "-O0"]
    define_macros = [("DEBUG", str(_DEBUG_LEVEL))]
    undef_macros = ["NDEBUG"]
else:
    extra_compile_args += ["-O3"]
    define_macros = [("NDEBUG", None)]
    undef_macros = []
if py_limited_api:
    define_macros.append(("Py_LIMITED_API", "0x03080000"))

setup(
    setup_requires=['setuptools_scm'],
    ext_modules=[
        Extension(
            "prism.language.sexp._parse",
            sources=[str(Path("prism") / "language" / "sexp" / "_parse.cpp")],
            extra_compile_args=extra_compile_args,
            define_macros=define_macros,
            undef_macros=undef_macros,
            py_limited_api=py_limited_api)
    ])
