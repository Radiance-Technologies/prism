"""
Test suite for prism.util.opam.
"""
import re
import tempfile
import unittest
from pathlib import Path

from prism.util.opam import OCamlVersion, OpamAPI, PackageFormula, Version
from prism.util.opam.formula import (
    Filter,
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
        config = self.test_switch.export()
        self.assertEqual(config.switch_name, self.test_switch_name)
        self.assertEqual(config.opam_root, self.test_switch.root)
        self.assertFalse(config.is_clone)
        # Compare against actual export file
        with tempfile.NamedTemporaryFile('r', dir=TEST_DIR) as f:
            self.test_switch.run(f"opam switch export {f.name}")
            actual = f.read()
        # remove optional fields to eliminate them from the comparison
        config.switch_name = None
        config.opam_root = None
        config.is_clone = None
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
        expected = PackageFormula(
            LogicalPF(
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
                    PackageConstraint("ocamlfind",
                                      Filter(Variable("build"))),
                    LogOp.AND,
                    LogicalPF(
                        PackageConstraint("num"),
                        LogOp.AND,
                        PackageConstraint(
                            "conf-findutils",
                            Filter(Variable("build")))))))
        self.assertEqual(actual, expected)

    def test_get_installed_version(self):
        """
        Test retrieval of installed versions.
        """
        self.assertIsNone(self.test_switch.get_installed_version("coq"))
        self.test_switch.install('coq', version="8.10.2", yes=True)
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

    def test_repo_add_remove(self):
        """
        Test the addition and removal of an opam repository.

        Test success by searching in output of `opam repo list`
        """
        repo_name = 'coq-released'
        repo_addr = 'https://coq.inria.fr/opam/released'

        r = self.test_switch.run("opam repo list")
        r.check_returncode()
        returned = r.stdout
        self.assertFalse(
            "coq-released "
            "https://coq.inria.fr/opam/released" in returned)

        self.test_switch.add_repo(repo_name, repo_addr)

        r = self.test_switch.run("opam repo list")
        r.check_returncode()
        returned = r.stdout
        self.assertTrue(
            "coq-released "
            "https://coq.inria.fr/opam/released" in returned)

        self.test_switch.remove_repo(repo_name)

        r = self.test_switch.run("opam repo list")
        r.check_returncode()
        returned = r.stdout
        self.assertFalse(
            "coq-released "
            "https://coq.inria.fr/opam/released" in returned)

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
