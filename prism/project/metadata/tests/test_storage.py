"""
Test suite for project metadata storage utilities.
"""

import os
import unittest
from copy import copy
from pathlib import Path

import seutil.io as io
from bidict import bidict

from prism.interface.coq.options import SerAPIOptions
from prism.project.metadata.dataclass import ProjectMetadata
from prism.project.metadata.storage import (
    CommandSequence,
    Context,
    MetadataStorage,
    ProjectSource,
    Revision,
)
from prism.tests.factories import ProjectFactory
from prism.util.io import Fmt
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
        self.metadata = list(reversed(ProjectMetadata.load(self.projects_yaml)))
        return super().setUp()

    def test_contains(self):
        """
        Verify that metadata existence in the storage can be tested.
        """
        storage = MetadataStorage()
        storage.insert(self.metadata[0])
        self.assertIn(self.metadata[0], storage)
        self.assertNotIn(self.metadata[1], storage)
        with self.assertRaises(TypeError):
            self.assertIn('gstew5_games', storage)

    def test_get_project_revisions(self):
        """
        Verify that function returns valid results for a project.
        """
        factory = ProjectFactory()
        metadata_storage = factory.metadata_storage
        for proj_name in factory.project_names:
            with self.subTest(proj_name):
                project = factory.projects[proj_name]

                g_p_revisions = metadata_storage.get_project_revisions
                revs = g_p_revisions(project.name, project.remote_url)
                self.assertTrue(len(revs) == 1)
                expected = factory.commit_shas[proj_name]
                self.assertTrue(next(iter(revs)) == expected)
        factory.cleanup()

    def test_git_extension_invariance(self):
        """
        Verify that the storage is invariant to URL ``.git`` extensions.
        """
        storage = MetadataStorage()
        metadata = self.metadata[0]
        for metadata in sorted(self.metadata):
            storage.insert(metadata)
        self.assertEqual(
            metadata,
            storage.get(
                metadata.project_name,
                metadata.project_url,
                metadata.commit_sha,
                metadata.coq_version,
                metadata.ocaml_version))
        assert metadata.project_url is not None
        self.assertEqual(
            metadata,
            storage.get(
                metadata.project_name,
                metadata.project_url + ".git",
                metadata.commit_sha,
                metadata.coq_version,
                metadata.ocaml_version))

    def test_insert(self):
        """
        Verify that metadata can be inserted.
        """
        metadata = ProjectMetadata("test", [], [], [])
        storage = MetadataStorage()
        storage.insert(metadata)
        with self.assertRaises(KeyError):
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
            0: SerAPIOptions.parse_args('-R .,Games')
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
            0: [1,
                2]
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

    def test_remove(self):
        """
        Verify that records can be removed.
        """
        storage = MetadataStorage(autofill=False)
        for metadata in self.metadata:
            storage.insert(metadata)
        base_metadata = self.metadata[0]
        override = self.metadata[1]
        # verify that the inherited values got wiped out
        with self.subTest("remove_base"):
            storage.remove(base_metadata)
            with self.assertRaises(KeyError):
                storage.populate(base_metadata)
            expected = ProjectMetadata(
                override.project_name,
                [],
                [],
                [],
                override.ocaml_version,
                override.coq_version,
                serapi_options=override.serapi_options,
                project_url=override.project_url,
                commit_sha=override.commit_sha)
            self.assertEqual(expected, storage.populate(override))
        # restore base metadata
        storage.insert(base_metadata)
        with self.subTest("remove_override"):
            storage.remove(override)
            expected = copy(base_metadata)
            expected.project_url = override.project_url
            expected.commit_sha = override.commit_sha
            expected.ocaml_version = override.ocaml_version
            self.assertEqual(expected, storage.populate(override))
            self.assertEqual(base_metadata, storage.populate(base_metadata))

    def test_union(self):
        """
        Verify that repositories can be merged.
        """
        expected_records = set(self.metadata)
        storages = []
        for metadata in self.metadata:
            storage = MetadataStorage()
            storage.insert(metadata)
            storages.append(storage)
        merged_storage = MetadataStorage.unions(*storages)
        self.assertEqual(expected_records, set(merged_storage))
        # reduction to identity
        self.assertEqual(MetadataStorage(), MetadataStorage.unions())
        # idempotent
        self.assertEqual(
            set(merged_storage),
            set(merged_storage.union(merged_storage)))

    def test_update(self):
        """
        Verify that records can be updated.
        """
        storage = MetadataStorage()
        for metadata in self.metadata:
            storage.insert(metadata)
        base_metadata = self.metadata[0]
        override = self.metadata[1]
        self.assertGreater(override, base_metadata)
        with self.subTest("update_inherited"):
            # verify inherited values get updated
            new_field_value = {'coq-released'}
            expected_base = copy(base_metadata)
            expected_base.opam_repos = new_field_value
            expected_override = copy(override)
            expected_override.opam_repos = new_field_value
            storage.update(
                base_metadata,
                cascade=False,
                opam_repos=new_field_value)
            updated_base = storage.populate(base_metadata)
            updated_override = storage.populate(override)
            self.assertEqual(updated_base, expected_base)
            self.assertEqual(updated_override, expected_override)
        with self.subTest("override_inherited"):
            # verify one can override a default through an update
            new_field_value = {'coq-mathcomp-ssreflect',
                               'coq-games'}
            expected_override.coq_dependencies = new_field_value
            storage.update(
                override,
                cascade=False,
                coq_dependencies=new_field_value)
            updated_base = storage.populate(base_metadata)
            updated_override = storage.populate(override)
            self.assertEqual(updated_base, expected_base)
            self.assertEqual(updated_override, expected_override)
        with self.subTest("override_inherited"):
            # verify one can update an overridden attribute
            new_field_value = {'coq-mathcomp-ssreflect'}
            expected_base.coq_dependencies = new_field_value
            storage.update(
                base_metadata,
                cascade=False,
                coq_dependencies=new_field_value)
            updated_base = storage.populate(base_metadata)
            updated_override = storage.populate(override)
            self.assertEqual(updated_base, expected_base)
            self.assertEqual(updated_override, expected_override)
        with self.subTest("update_cascade"):
            # verify one can cascade an update to an inherited attribute
            new_field_value = {'fake-coq-released'}
            expected_base.opam_repos = new_field_value
            expected_override.opam_repos = new_field_value
            storage.update(override, cascade=True, opam_repos=new_field_value)
            updated_base = storage.populate(base_metadata)
            updated_override = storage.populate(override)
            self.assertEqual(updated_base, expected_base)
            self.assertEqual(updated_override, expected_override)
        with self.subTest("update_implied"):
            # verify one can update an implied context
            new_field_value = {'coq-games'}
            expected_novel = copy(expected_base)
            expected_novel.project_url = override.project_url
            expected_novel.commit_sha = "fake_test_sha"
            storage.update(
                expected_novel,
                cascade=False,
                coq_dependencies=new_field_value)
            updated_base = storage.populate(base_metadata)
            updated_novel = storage.populate(expected_novel)
            expected_novel.coq_dependencies = new_field_value
            updated_override = storage.populate(override)
            self.assertEqual(updated_novel, expected_novel)
            # verify other metadata is not affected
            self.assertEqual(updated_base, expected_base)
            self.assertEqual(updated_override, expected_override)

    def test_serialization(self):
        """
        Verify that the storage can be serialized and deserialized.
        """
        storage = MetadataStorage()
        for metadata in self.metadata:
            storage.insert(metadata)
        with self.subTest("inverse"):
            # deserialization is the inverse of serialization
            serialized = io.serialize(storage, Fmt.json)
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
        with self.subTest("deterministic"):
            serialized_1 = io.serialize(storage, Fmt.json)
            serialized_2 = io.serialize(storage, Fmt.json)
            self.assertEqual(serialized_1, serialized_2)


if __name__ == '__main__':
    unittest.main()
