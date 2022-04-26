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

    def test_serialize_to_str(self):
        """
        Ensure deserialized dataclass object can be properly serialized.
        """
        yaml_path = "prism/project/tests/projects.yml"
        metadata_objs = load_metadata_from_yaml(yaml_path)
        metadata_obj = metadata_objs[0]

        # Only two projects in the YAML file contain all 12 attributes
        self.assertEqual(
            str(metadata_obj.serialize_to_str()),
            "{\'full_name\': "
            + "\'DistributedComponents_disel\', \'short_name\': \'disel\', "
            + "\'id\': \'disel\', \'url\': "
            + "\'https://github.com/DistributedComponents/disel\', "
            + "\'sha\': \'e8aa80c486ec618888b6d0c801da7f61b6046daa\', "
            + "\'tag\': \'v2.1\', \'dependencies\': "
            + "[\'math-comp_math-comp\', \'imdea-software_fcsl-pcm\'], "
            + "\'build_cmd\': \'make -j8 -C Core\', "
            + "\'install_cmd\': \'make -C Core install\', "
            + "\'ignore_path_regex\': \'Core/InjectionOld\\\\.v|Examples/.*\', "
            + "\'serapi_options\': \'-R Core,DiSeL\', \'group\': \'t3\'}")

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
        self.assertEqual(metadata_obj.full_name, new_metadata_obj.full_name)
        self.assertEqual(metadata_obj.short_name, new_metadata_obj.short_name)
        self.assertEqual(metadata_obj.id, new_metadata_obj.id)
        self.assertEqual(metadata_obj.url, new_metadata_obj.url)
        self.assertEqual(metadata_obj.sha, new_metadata_obj.sha)
        self.assertEqual(metadata_obj.tag, new_metadata_obj.tag)
        self.assertEqual(
            metadata_obj.dependencies,
            new_metadata_obj.dependencies)
        self.assertEqual(metadata_obj.build_cmd, new_metadata_obj.build_cmd)
        self.assertEqual(metadata_obj.install_cmd, new_metadata_obj.install_cmd)
        self.assertEqual(
            metadata_obj.ignore_path_regex,
            new_metadata_obj.ignore_path_regex)
        self.assertEqual(
            metadata_obj.serapi_options,
            new_metadata_obj.serapi_options)
        self.assertEqual(metadata_obj.group, new_metadata_obj.group)

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

        self.assertEqual(metadata_obj_1.full_name, new_metadata_obj_1.full_name)
        self.assertEqual(
            metadata_obj_1.short_name,
            new_metadata_obj_1.short_name)
        self.assertEqual(metadata_obj_1.id, new_metadata_obj_1.id)
        self.assertEqual(metadata_obj_1.url, new_metadata_obj_1.url)
        self.assertEqual(metadata_obj_1.sha, new_metadata_obj_1.sha)
        self.assertEqual(metadata_obj_1.tag, new_metadata_obj_1.tag)
        self.assertEqual(
            metadata_obj_1.dependencies,
            new_metadata_obj_1.dependencies)
        self.assertEqual(metadata_obj_1.build_cmd, new_metadata_obj_1.build_cmd)
        self.assertEqual(
            metadata_obj_1.install_cmd,
            new_metadata_obj_1.install_cmd)
        self.assertEqual(
            metadata_obj_1.ignore_path_regex,
            new_metadata_obj_1.ignore_path_regex)
        self.assertEqual(
            metadata_obj_1.serapi_options,
            new_metadata_obj_1.serapi_options)
        self.assertEqual(metadata_obj_1.group, new_metadata_obj_1.group)

        self.assertEqual(metadata_obj_2.full_name, new_metadata_obj_2.full_name)
        self.assertEqual(
            metadata_obj_2.short_name,
            new_metadata_obj_2.short_name)
        self.assertEqual(metadata_obj_2.id, new_metadata_obj_2.id)
        self.assertEqual(metadata_obj_2.url, new_metadata_obj_2.url)
        self.assertEqual(metadata_obj_2.sha, new_metadata_obj_2.sha)
        self.assertEqual(metadata_obj_2.tag, new_metadata_obj_2.tag)
        self.assertEqual(
            metadata_obj_2.dependencies,
            new_metadata_obj_2.dependencies)
        self.assertEqual(metadata_obj_2.build_cmd, new_metadata_obj_2.build_cmd)
        self.assertEqual(
            metadata_obj_2.install_cmd,
            new_metadata_obj_2.install_cmd)
        self.assertEqual(
            metadata_obj_2.ignore_path_regex,
            new_metadata_obj_2.ignore_path_regex)
        self.assertEqual(
            metadata_obj_2.serapi_options,
            new_metadata_obj_2.serapi_options)
        self.assertEqual(metadata_obj_2.group, new_metadata_obj_2.group)

        os.remove("prism/project/tests/test.yml")


if __name__ == '__main__':
    unittest.main()
