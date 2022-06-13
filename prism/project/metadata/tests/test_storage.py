"""
Test suite for project metadata storage utilities.
"""

import os
import unittest
from pathlib import Path

import seutil.io as io
from bidict import bidict

from prism.project.metadata.dataclass import ProjectMetadata
from prism.project.metadata.storage import (
    CommandSequence,
    Context,
    MetadataStorage,
    ProjectSource,
    Revision,
)
from prism.util.opam import OCamlVersion

TEST_DIR = Path(__file__).parent


class TestMetadataStorage(unittest.TestCase):
    """
    Test suite for `MetadataStorage`.
    """

    def setUp(self) -> None:
        """
        Set up common metadata.
        """
        self.projects_yaml = TEST_DIR / "projects.yml"
        self.metadata = ProjectMetadata.load(self.projects_yaml)
        return super().setUp()

    def test_insert(self):
        """
        Verify that metadata can be inserted.
        """
        metadata = ProjectMetadata("test", [], [], [])
        storage = MetadataStorage()
        storage.insert(metadata)
        expected = MetadataStorage()
        expected.projects = {'test'}
        expected.project_sources = {ProjectSource('test',
                                                  None)}
        expected.revisions = {Revision(ProjectSource('test',
                                                     None),
                                       None)}
        expected.contexts = {
            Context(Revision(ProjectSource('test',
                                           None),
                             None),
                    None,
                    None): 0
        }
        expected.indices = {
            'contexts': 1,
            'command_sequences': 0,
            'ocaml_packages': 0,
            'opam_repositories': 0
        }
        self.assertEqual(storage, expected)
        self.assertEqual(storage.get("test"), metadata)

    def test_iter(self):
        """
        Verify that individual records can be retrieved via iteration.
        """
        storage = MetadataStorage()
        for metadata in self.metadata:
            storage.insert(metadata)
        self.assertEqual(set(self.metadata), set(iter(storage)))

    def test_override(self):
        """
        Verify that non-overridden data is not duplicated.
        """
        storage = MetadataStorage()
        for metadata in sorted(self.metadata):
            storage.insert(metadata)
        expected = MetadataStorage()
        expected.projects = {'gstew5_games'}
        expected.project_sources = {
            ProjectSource('gstew5_games',
                          None),
            ProjectSource('gstew5_games',
                          'https://github.com/gstew5/games')
        }
        expected.revisions = {
            Revision(ProjectSource('gstew5_games',
                                   None),
                     None),
            Revision(
                ProjectSource(
                    'gstew5_games',
                    'https://github.com/gstew5/games'),
                '3d3bd31c7e4d1ea6f4b5a6815bca5c0a039b204f')
        }
        expected.contexts = dict(
            [
                (
                    Context(
                        Revision(ProjectSource('gstew5_games',
                                               None),
                                 None),
                        OCamlVersion.parse('8.10.2'),
                        None),
                    0),
                (
                    Context(
                        Revision(
                            ProjectSource(
                                'gstew5_games',
                                'https://github.com/gstew5/games'),
                            '3d3bd31c7e4d1ea6f4b5a6815bca5c0a039b204f'),
                        OCamlVersion.parse('8.10.2'),
                        OCamlVersion.parse('4.07.1')),
                    1)
            ])
        expected.serapi_options = {
            0: '-R .,Games'
        }
        expected.build_cmd = {
            0: 0
        }
        expected.install_cmd = {
            0: 1
        }
        expected.clean_cmd = {
            0: 2
        }
        expected.opam_repos = {
            0: {0,
                1}
        }
        expected.indices = {
            'contexts': 2,
            'command_sequences': 3,
            'ocaml_packages': 3,
            'opam_repositories': 2
        }
        expected.coq_dependencies = {
            0: {0}
        }
        expected.opam_dependencies = {
            0: {1,
                2}
        }
        expected.ignore_path_regex = {
            0: {'gstew5_games/test_suite/.*'}
        }
        expected.ocaml_packages = bidict(
            {
                'dependency_1': 0,
                'pandas': 1,
                'numpy': 2,
            })
        expected.opam_repositories = bidict({
            '1.0.0': 0,
            '1.0.1': 1
        })
        expected.command_sequences = bidict(
            {
                CommandSequence(['make -j8']): 0,
                CommandSequence(['make',
                                 'make install']): 1,
                CommandSequence(['make clean']): 2
            })
        try:
            self.assertTrue(storage, expected)
        except AssertionError:
            # due to nondeterminism of sets
            expected.ocaml_packages = bidict(
                {
                    'dependency_1': 0,
                    'pandas': 2,
                    'numpy': 1,
                })
            self.assertTrue(storage, expected)
        with self.assertRaises(KeyError):
            storage.insert(self.metadata[0])

    def test_serialization(self):
        """
        Verify that the storage can be serialized and deserialized.
        """
        storage = MetadataStorage()
        for metadata in self.metadata:
            storage.insert(metadata)
        with self.subTest("inverse"):
            # deserialization is the inverse of serialization
            serialized = io.serialize(storage, io.Fmt.json)
            self.assertEqual(
                storage,
                io.deserialize(serialized,
                               clz=MetadataStorage))
        with self.subTest("to_file"):
            storage_file = TEST_DIR / 'storage.yml'
            # verify metadata can be dumped to and loaded from file
            MetadataStorage.dump(storage, storage_file)
            loaded = MetadataStorage.load(storage_file)
            self.assertEqual(storage, loaded)
            os.remove(storage_file)


if __name__ == '__main__':
    unittest.main()
