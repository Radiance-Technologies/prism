"""
Test suite for `prism.project.metadata`.
"""

import os
import unittest

from prism.project.metadata import ProjectMetadata


class TestProjectMetadata(unittest.TestCase):
    """
    Test suite for `ProjectMetadata`.
    """

    def test_load_metadata_from_yaml(self):
        """
        Ensure import .yaml file can be deserialized properly.
        """
        yaml_path_complete = "prism/project/tests/projects.yml"
        yaml_path_incomplete = "prism/project/tests/projects_incomplete.yml"
        metadata_objs = ProjectMetadata.load(yaml_path_complete)

        # Only two projects in the YAML file contain
        # all required attributes
        self.assertEqual(len(metadata_objs), 2)

        # Assert error is thrown when required field missing
        self.assertRaises(TypeError, ProjectMetadata.load, yaml_path_incomplete)

    def test_serialize_to_file(self):
        """
        Tests YAML files are serialized properly.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = ProjectMetadata.load(yaml_path)
        metadata_obj = metadata_objs[0]
        ProjectMetadata.dump([metadata_obj], "prism/project/tests/test.yml")

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile("prism/project/tests/test.yml"))

        new_metadata_obj = ProjectMetadata.load(
            "prism/project/tests/test.yml")[0]

        # Test that data is consistent after being
        # serialized/deserialized
        self.assertEqual(metadata_obj, new_metadata_obj)

        os.remove("prism/project/tests/test.yml")

    def test_serialize_to_existing_file(self):
        """
        Tests that appending to an existing YAML file is working.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = ProjectMetadata.load(yaml_path)
        metadata_obj_1 = metadata_objs[0]
        metadata_obj_2 = metadata_objs[1]
        ProjectMetadata.dump([metadata_obj_1], "prism/project/tests/test.yml")
        ProjectMetadata.dump([metadata_obj_2], "prism/project/tests/test.yml")

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile("prism/project/tests/test.yml"))

        # Test that both metadata objects are deserialized correctly
        new_metadata_lst = ProjectMetadata.load("prism/project/tests/test.yml")
        self.assertEqual(len(new_metadata_lst), 2)

        # Test that data from the first project is consistent
        # after being serialized/deserialized
        new_metadata_obj_1 = new_metadata_lst[0]
        new_metadata_obj_2 = new_metadata_lst[1]

        self.assertEqual(new_metadata_obj_1, metadata_obj_1)
        self.assertEqual(new_metadata_obj_2, metadata_obj_2)

        os.remove("prism/project/tests/test.yml")

    def test_serialize_to_file_multi(self):
        """
        Tests that serialization of a list of metadata objecs works.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = ProjectMetadata.load(yaml_path)
        ProjectMetadata.dump(metadata_objs, "prism/project/tests/test.yml")

        # Test that .yml file is created properly
        self.assertTrue(os.path.isfile("prism/project/tests/test.yml"))

        # Test that both metadata objects are deserialized correctly
        new_metadata_lst = ProjectMetadata.load("prism/project/tests/test.yml")
        self.assertEqual(len(new_metadata_lst), 2)

        # Test that data from the first project is consistent
        # after being serialized/deserialized
        new_metadata_obj_1 = new_metadata_lst[0]
        new_metadata_obj_2 = new_metadata_lst[1]

        self.assertEqual(new_metadata_obj_1, metadata_objs[0])
        self.assertEqual(new_metadata_obj_2, metadata_objs[1])

        os.remove("prism/project/tests/test.yml")


if __name__ == '__main__':
    unittest.main()
