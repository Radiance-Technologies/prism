"""
Test suite for project metadata storage utilities.
"""
import os
import unittest
from pathlib import Path

import seutil.io as io

from prism.project.metadata.dataclass import ProjectMetadata
from prism.project.metadata.storage import (
    Context,
    MetadataStorage,
    ProjectSource,
    Revision,
)

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
        metadata = ProjectMetadata("test", "", [], [], [])
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
        expected.next_context_id = 1
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
