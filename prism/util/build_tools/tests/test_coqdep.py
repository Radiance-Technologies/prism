"""
Test suite for prism.util.opam.
"""
import os
import unittest

import git
import networkx as nx

from prism.util.build_tools.coqdep import CoqDepAPI
from prism.util.opam import OpamAPI, OpamSwitch
from prism.util.opam.switch import _allow_unsafe_clone


class TestOpamAPI(unittest.TestCase):
    """
    Test suite for `OpamAPI`.
    """

    test_switch_name = "test_switch"
    ocaml_version = "4.07.1"
    clone = None

    def test_create_switch(self):
        """
        Verify that switches can be created and not overwritten.
        """
        coqdep = CoqDepAPI()
        coqdep.order_dependencies(
            ["./Test.v",
             "./Residuals.v"],
            self.test_switch)

    @classmethod
    def setUpClass(cls):
        """
        Set up a test switch and download Lambda.
        """
        cls.test_path = os.path.dirname(__file__)
        # HEAD commits as of August 16, 2022
        cls.project_names = {"lambda"}
        cls.master_hashes = {
            "lambda": "f531eede1b2088eff15b856558ec40f177956b96"
        }
        cls.target_projects = {
            "lambda": "coq-contribs/lambda"
        }
        cls.repo_paths = {}
        cls.repos = {}
        cls.projects = {}
        cls.metadatas = {}
        for project_name, project in cls.target_projects.items():
            project_path = os.path.join(cls.test_path, project_name)
            cls.repo_paths[project_name] = project_path
            try:
                repo = git.Repo.clone_from(
                    f"https://github.com/{project}",
                    project_path)
            except git.GitCommandError:
                repo = git.Repo(project_path)

        cls.test_switch = OpamAPI.create_switch(
            cls.test_switch_name,
            cls.ocaml_version)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove the test switch.

        Doubles as test for switch removal.
        """
        OpamAPI.remove_switch(cls.test_switch)
        with cls.assertRaises(TestOpamAPI(), ValueError):
            OpamAPI.remove_switch(cls.test_switch)
        with cls.assertRaises(TestOpamAPI(), ValueError):
            OpamAPI.remove_switch(cls.test_switch_name)
        OpamAPI.remove_switch("test_cloned_switch")
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))


if __name__ == '__main__':
    unittest.main()
