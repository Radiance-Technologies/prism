"""
Test suite for project metadata storage utilities.
"""
import unittest
from pathlib import Path

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
        self.assertEqual(self.metadata, list(iter(storage)))


if __name__ == '__main__':
    unittest.main()
