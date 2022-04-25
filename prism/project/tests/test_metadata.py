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


if __name__ == '__main__':
    unittest.main()
