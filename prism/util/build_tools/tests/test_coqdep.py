"""
Test suite for `prism.util.build_tools.coqdep`.
"""
import os
import shutil
import unittest

import git
import networkx as nx

from prism.util.build_tools.coqdep import (
    get_dependencies,
    is_valid_topological_sort,
    make_dependency_graph,
    order_dependencies,
)
from prism.util.radpytools.os import pushd


class TestCoqDep(unittest.TestCase):
    """
    Test suite for `coqdep` utility function wrappers.
    """

    def test_is_valid_topological_sort(self):
        """
        Test that topological sorts can be verified.
        """
        edges = {
            'Redexes.v': [],
            'Reduction.v': ['Redexes.v'],
            'Terms.v': ['Reduction.v',
                        'Redexes.v'],
            'Test.v': ['Terms.v',
                       'Reduction.v',
                       'Redexes.v']
        }
        dg = nx.DiGraph(edges)

        expected = ["Test.v", "Terms.v", "Reduction.v", "Redexes.v"]
        self.assertTrue(is_valid_topological_sort(dg, expected))

    def test_get_dependencies(self):
        """
        Verify that dependencies can be sorted.
        """
        with pushd(self.repo_paths["lambda"]):
            files = os.listdir("./")
            files = [x for x in files if x[-2 :] == '.v']
            deps = get_dependencies("Redexes.v")
            expected = ["Test.v", "Terms.v", "Reduction.v"]
            for file in expected:
                self.assertTrue(file in deps)

    def test_make_dep_graph(self):
        """
        Check that a dependency graph can be made from a list of files.
        """
        edges = {}
        edges['Substitution.v'] = []
        edges['Marks.v'] = []
        edges['Redexes.v'] = ['Substitution.v', 'Marks.v']
        edges['Reduction.v'] = ['Redexes.v', 'Marks.v', 'Substitution.v']
        edges['Terms.v'] = [
            'Reduction.v',
            'Redexes.v',
            'Marks.v',
            'Substitution.v'
        ]
        edges['Test.v'] = [
            'Terms.v',
            'Reduction.v',
            'Redexes.v',
            'Substitution.v',
            'Marks.v'
        ]
        expected = nx.DiGraph(edges)

        files = [
            'Test.v',
            'Terms.v',
            'Reduction.v',
            'Redexes.v',
            'Marks.v',
            'Substitution.v'
        ]
        with pushd(self.repo_paths["lambda"]):
            dg = make_dependency_graph(files)
        self.assertTrue(nx.utils.misc.edges_equal(dg.edges, expected.edges))

    def test_order_dependencies(self):
        """
        Verify that dependencies can be sorted.
        """
        with pushd(self.repo_paths["lambda"]):
            files = os.listdir("./")
            files = [x for x in files if x.endswith('.v')]
            ordered = order_dependencies(files)
            graph = make_dependency_graph(files)
            self.assertTrue(is_valid_topological_sort(graph, ordered))

    @classmethod
    def setUpClass(cls):
        """
        Download Lambda.
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
        """
        for project_name, repo in cls.repos.items():
            del repo
            shutil.rmtree(os.path.join(cls.repo_paths[project_name]))


if __name__ == '__main__':
    unittest.main()
