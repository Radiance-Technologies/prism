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
