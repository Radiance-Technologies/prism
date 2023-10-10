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
Test suite for prism.util.opam.
"""
import re
import tempfile
import unittest
from functools import partial
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired

from prism.util.opam import OCamlVersion, OpamAPI, Version
from prism.util.opam.formula import (
    FilterAtom,
    FilterVF,
    LogicalPF,
    LogicalVF,
    LogOp,
    PackageConstraint,
    RelOp,
    Variable,
    VersionConstraint,
)

TEST_DIR = Path(__file__).parent


class TestOpamSwitch(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    test_switch_name = "test_switch"
    ocaml_version = "4.07.1"

    def test_export(self):
        """
        Verify that exported switch configurations match file exports.
        """
        config = self.test_switch.export(include_metadata=True)
        self.assertEqual(config.switch_name, self.test_switch_name)
        self.assertEqual(config.opam_root, self.test_switch.root)
        self.assertFalse(config.is_clone)
        self.assertTrue(config.package_metadata)
        # Compare against actual export file
        with tempfile.NamedTemporaryFile('r', dir=TEST_DIR) as f:
            self.test_switch.run(f"opam switch export {f.name}")
            actual = f.read()
        # remove optional fields to eliminate them from the comparison
        config.switch_name = None
        config.opam_root = None
        config.is_clone = None
        config.package_metadata = []
        # normalize whitespace
        actual = actual.replace("[", "[ ").replace("]", " ]")
        actual = ' '.join(actual.split())
        expected = ' '.join(str(config).split())
        self.assertEqual(expected, actual)

    def test_get_available_versions(self):
        """
        Test retrieval of available versions for a single package.

        Indirectly test by comparing a pretty-printed version of the
        retrieved versions with the command-line output.
        """
        pkg = 'ocaml'
        r = self.test_switch.run(f"opam show -f all-versions {pkg}")
        r.check_returncode()
        expected = re.sub(r"\s+", " ", r.stdout).strip()
        actual = self.test_switch.get_available_versions(pkg)
        self.assertIsInstance(actual[0], Version)
        self.assertEqual(" ".join(str(v) for v in actual), expected)

    def test_get_dependencies(self):
        """
        Test retrieval of dependencies for a single package.
        """
        actual = self.test_switch.get_dependencies("coq", "8.10.2")
        expected = LogicalPF(
            PackageConstraint(
                "ocaml",
                LogicalVF(
                    VersionConstraint(RelOp.GEQ,
                                      OCamlVersion(4,
                                                   '05',
                                                   0)),
                    LogOp.AND,
                    VersionConstraint(RelOp.LT,
                                      OCamlVersion(4,
                                                   10)))),
            LogOp.AND,
            LogicalPF(
                PackageConstraint(
                    "ocamlfind",
                    FilterVF(FilterAtom(Variable("build")))),
                LogOp.AND,
                LogicalPF(
                    PackageConstraint("num"),
                    LogOp.AND,
                    PackageConstraint(
                        "conf-findutils",
                        FilterVF(FilterAtom(Variable("build")))))))
        self.assertEqual(actual, expected)

    def test_get_installed_version(self):
        """
        Test retrieval of installed versions.
        """
        self.assertIsNone(self.test_switch.get_installed_version("coq"))
        self.test_switch.install('coq', version="8.10.2")
        version = self.test_switch.get_installed_version("coq")
        self.assertEqual(version, "8.10.2")
        version = self.test_switch.get_installed_version("ocaml")
        self.assertEqual(version, self.ocaml_version)

    def test_install_remove(self):
        """
        Test installation and removal of a single package.

        Test success by searching in output of `opam list -i`
        """
        pkg = 'coq-shell'
        r = self.test_switch.run(f"opam list -i {pkg}")
        r.check_returncode()
        returned = r.stderr
        self.assertTrue("No matches found" in returned)

        self.test_switch.install(pkg, version='1')

        r = self.test_switch.run(f"opam list -i {pkg}")
        r.check_returncode()
        returned = r.stdout
        self.assertTrue("coq-shell 1           Simplified" in returned)

        self.test_switch.remove_pkg(pkg)

        r = self.test_switch.run(f"opam list -i {pkg}")
        r.check_returncode()
        returned = r.stderr
        self.assertTrue("No matches found" in returned)

    def test_install_formula(self):
        """
        Test installation of just a package's dependencies from formula.
        """
        formula = self.test_switch.get_dependencies("coq", "8.10.2")
        self.test_switch.install_formula(formula)
        deps = formula.packages
        installed_deps = {
            dep: self.test_switch.get_installed_version(dep) for dep in deps
        }
        installed_deps = {
            k: Version.parse(v) for k,
            v in installed_deps.items() if v is not None
        }
        self.assertTrue(installed_deps)
        self.assertIn((installed_deps,
                       {
                           'build': True
                       }),
                      formula)

    def test_repo_add_remove(self):
        """
        Test the addition and removal of an opam repository.

        Test success by searching in output of `opam repo list`
        """
        repo_name = 'coq-released'
        repo_addr = 'https://coq.inria.fr/opam/released'
        first_op = partial(self.test_switch.add_repo, repo_addr=repo_addr)
        second_op = self.test_switch.remove_repo
        first_assert = self.assertIn
        second_assert = self.assertNotIn

        r = self.test_switch.run("opam repo list")
        r.check_returncode()
        returned = r.stdout
        if ("coq-released https://coq.inria.fr/opam/released" in returned):
            first_op, second_op = second_op, first_op
            first_assert, second_assert = second_assert, first_assert

        first_op(repo_name)

        r = self.test_switch.run("opam repo list")
        r.check_returncode()
        returned = r.stdout
        first_assert(
            "coq-released https://coq.inria.fr/opam/released",
            returned)

        second_op(repo_name)

        r = self.test_switch.run("opam repo list")
        r.check_returncode()
        returned = r.stdout
        second_assert(
            "coq-released https://coq.inria.fr/opam/released",
            returned)

    def test_limits(self):
        """
        Verify resource limits on run commands.
        """
        self.assertRaises(
            TimeoutExpired,
            self.test_switch.run,
            "sleep 5",
            max_runtime=3)
        self.assertRaises(
            CalledProcessError,
            self.test_switch.run,
            "python -c 'a=[1 for _ in range(int(1e8))]'",
            max_memory=int(4 * 1e7),
        )
        output = self.test_switch.run(
            "python -c 'a=[1 for _ in range(int(1e8))]'",
            max_memory=int(4 * 1e7),
            check=False,
        )
        self.assertIn("MemoryError", output.stderr)

    @classmethod
    def setUpClass(cls):
        """
        Set up a test switch.
        """
        cls.test_switch = OpamAPI.create_switch(
            cls.test_switch_name,
            cls.ocaml_version)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove the test switch.
        """
        OpamAPI.remove_switch(cls.test_switch)


if __name__ == '__main__':
    unittest.main()
