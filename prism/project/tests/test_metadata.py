"""
Test suite for `prism.project.metadata`.
"""

import os
import unittest

from prism.project.metadata import load_metadata_from_yaml


class TestProjectMetadata(unittest.TestCase):
    """
    Test suite for `ProjectMetadata`.
    """

    def test_load_metadata_from_yaml(self):
        """
        Ensure import .yaml file can be deserialized properly.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = load_metadata_from_yaml(yaml_path)

        # Only two projects in the YAML file contain all 12 attributes
        self.assertEqual(len(metadata_objs), 2)

    def test_serialize_to_file(self):
        """
        Tests YAML files are serialized properly.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = load_metadata_from_yaml(yaml_path)
        metadata_obj = metadata_objs[0]
        metadata_obj.serialize_to_file("test.yml")

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile("test.yml"))

        new_metadata_obj = load_metadata_from_yaml("test.yml")[0]

        # Test that data is consistent after being
        # serialized/deserialized
        self.assertEqual(metadata_obj, new_metadata_obj)

        os.remove("test.yml")

    def test_serialize_to_file_multi(self):
        """
        Tests YAML file with multiple projects are serialized properly.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = load_metadata_from_yaml(yaml_path)
        metadata_obj_1 = metadata_objs[0]
        metadata_obj_2 = metadata_objs[1]
        metadata_obj_1.serialize_to_file("prism/project/tests/test.yml")
        metadata_obj_2.serialize_to_file("prism/project/tests/test.yml")

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile("prism/project/tests/test.yml"))

        # Test that both metadata objects are deserialized correctly
        new_metadata_lst = load_metadata_from_yaml(
            "prism/project/tests/test.yml")
        self.assertEqual(len(new_metadata_lst), 2)

        # Test that data from the first project is consistent
        # after being serialized/deserialized
        new_metadata_obj_1 = new_metadata_lst[0]
        new_metadata_obj_2 = new_metadata_lst[1]

        self.assertEqual(new_metadata_obj_1, metadata_obj_1)
        self.assertEqual(new_metadata_obj_2, metadata_obj_2)

        os.remove("prism/project/tests/test.yml")


if __name__ == '__main__':
    unittest.main()
