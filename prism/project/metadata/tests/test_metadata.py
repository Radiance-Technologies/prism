"""
Test suite for `prism.project.metadata`.
"""

import os
import unittest
from pathlib import Path

from prism.project.metadata import ProjectMetadata

TEST_DIR = Path(__file__).parent


class TestProjectMetadata(unittest.TestCase):
    """
    Test suite for `ProjectMetadata`.
    """

    def setUp(self) -> None:
        """
        Set up common file paths for unit tests.
        """
        self.yaml_path_complete = TEST_DIR / "projects.yml"
        self.yaml_path_incomplete = TEST_DIR / "projects_incomplete.yml"
        self.test_yaml_path = TEST_DIR / "test.yml"
        return super().setUp()

    def test_load_metadata_from_yaml(self):
        """
        Ensure import .yaml file can be deserialized properly.
        """
        metadata_objs = ProjectMetadata.load(self.yaml_path_complete)

        # Only two projects in the YAML file contain
        # all required attributes
        self.assertEqual(len(metadata_objs), 2)

        # Assert error is thrown when required field missing
        self.assertRaises(
            TypeError,
            ProjectMetadata.load,
            self.yaml_path_incomplete)

    def test_serialize_to_file(self):
        """
        Tests YAML files are serialized properly.
        """
        metadata_objs = ProjectMetadata.load(self.yaml_path_complete)
        metadata_obj = metadata_objs[0]
        ProjectMetadata.dump([metadata_obj], self.test_yaml_path)

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile(self.test_yaml_path))

        new_metadata_obj = ProjectMetadata.load(self.test_yaml_path)[0]

        # Test that data is consistent after being
        # serialized/deserialized
        self.assertEqual(metadata_obj, new_metadata_obj)

        os.remove(self.test_yaml_path)

    def test_serialize_to_file_multi(self):
        """
        Tests that serialization of a list of metadata objecs works.
        """
        metadata_objs = ProjectMetadata.load(self.yaml_path_complete)
        ProjectMetadata.dump(metadata_objs, self.test_yaml_path)

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile(self.test_yaml_path))

        # Test that both metadata objects are deserialized correctly
        new_metadata_lst = ProjectMetadata.load(self.test_yaml_path)
        self.assertEqual(len(new_metadata_lst), 2)

        # Test that data from the first project is consistent
        # after being serialized/deserialized
        new_metadata_obj_1 = new_metadata_lst[0]
        new_metadata_obj_2 = new_metadata_lst[1]

        self.assertEqual(new_metadata_obj_1, metadata_objs[0])
        self.assertEqual(new_metadata_obj_2, metadata_objs[1])

        os.remove(self.test_yaml_path)


if __name__ == '__main__':
    unittest.main()
