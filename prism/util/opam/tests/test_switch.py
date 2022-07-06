"""
Test suite for prism.util.opam.
"""
import re
import unittest
from typing import Dict

from prism.util.opam import OCamlVersion, OpamAPI, Version, VersionConstraint


class TestOpamSwitch(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    test_switch_name = "test_switch"
    ocaml_version = "4.07.1"

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
        expected: Dict[str, VersionConstraint]
        expected = {
            "ocaml":
                VersionConstraint(
                    OCamlVersion(4,
                                 '05',
                                 0),
                    OCamlVersion(4,
                                 10),
                    True,
                    False),
            "ocamlfind":
                VersionConstraint(),
            "num":
                VersionConstraint(),
            "conf-findutils":
                VersionConstraint()
        }
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
