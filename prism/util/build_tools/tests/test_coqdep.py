"""
Test suite for prism.util.opam.
"""
import os
import shutil
import unittest

import git

import prism.util.radpytools.os

from prism.util.build_tools.coqdep import order_dependencies
from prism.util.opam import OpamAPI


class TestOpamCoqDepAPI(unittest.TestCase):
    """
    Test suite for `CoqDepAPI`.
    """

    test_switch_name = "test_switch"
    ocaml_version = "4.07.1"
    clone = None

    def test_order_dependencies(self):
        """
        Verify that dependencies can be sorted.
        """
        with prism.util.radpytools.os.pushd("./lambda"):
            files = os.listdir("./")
            files = [x for x in files if x[-2 :] == '.v']
            ordered = order_dependencies(files, OpamAPI.active_switch)
            expected = [
                'Test.vo',
                'Terms.vo',
                'Reduction.vo',
                'Redexes.vo',
                'Marks.vo',
                'Substitution.vo',
                'Residuals.vo',
                'Simulation.vo',
                'Cube.vo',
                'Confluence.vo',
                'Conversion.vo',
                'Lambda.vo'
            ]
            self.assertEqual(ordered, expected)

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
            cls.repos[project_name] = repo

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove the test switch.

        Doubles as test for switch removal.
        """
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))


if __name__ == '__main__':
    unittest.main()
