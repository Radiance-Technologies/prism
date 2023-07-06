"""
Test module for prism.data.project module.
"""
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import unittest
from itertools import chain
from pathlib import Path

import git
import pytest

from prism.data.document import CoqDocument
from prism.interface.coq.iqr import IQR
from prism.interface.coq.options import SerAPIOptions
from prism.language.gallina.analyze import SexpInfo
from prism.project.base import SEM, Project, SentenceExtractionMethod
from prism.project.metadata.dataclass import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage
from prism.project.repo import ProjectRepo
from prism.tests import _COQ_EXAMPLES_PATH
from prism.util.opam.switch import OpamSwitch
from prism.util.radpytools.os import pushd


class TestProjectSetup(unittest.TestCase):
    """
    Setup infrastructure for project testing.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up shared project files for unit tests.
        """
        expected_filename = os.path.join(
            _COQ_EXAMPLES_PATH,
            "split_by_sentence_expected.json")
        cls.test_contents = {}
        cls.document = {}
        cls.test_list = {}
        cls.test_glom_list = {}
        coq_example_files = ["simple", "nested", "Alphabet"]
        for coq_file in coq_example_files:
            test_filename = os.path.join(_COQ_EXAMPLES_PATH, f"{coq_file}.v")
            with open(test_filename, "rt") as f:
                cls.test_contents[coq_file] = f.read()
            cls.document[coq_file] = CoqDocument(
                test_filename,
                cls.test_contents[coq_file],
                project_path=_COQ_EXAMPLES_PATH,
                serapi_options=SerAPIOptions.empty(_COQ_EXAMPLES_PATH))
            with open(expected_filename, "rt") as f:
                contents = json.load(f)
                cls.test_list[coq_file] = contents[f"{coq_file}_test_list"]
                cls.test_glom_list[coq_file] = contents[
                    f"{coq_file}_test_glom_list"]
        # set up artifacts for test_build_and_get_igr
        test_path = Path(__file__).parent
        repo_path = test_path / "coq-sep-logic"
        if not os.path.exists(repo_path):
            test_repo = git.Repo.clone_from(
                "https://github.com/tchajed/coq-sep-logic",
                repo_path)
        else:
            test_repo = git.Repo(repo_path)
        metadata = ProjectMetadata.load(
            _COQ_EXAMPLES_PATH / "coq_sep_logic.yml")[0]
        storage = MetadataStorage()
        storage.insert(metadata.at_level(0))
        storage.insert(metadata)
        test_repo.git.checkout(metadata.commit_sha)
        cls.test_iqr_project = ProjectRepo(
            repo_path,
            metadata_storage=storage,
            sentence_extraction_method=SEM.HEURISTIC,
            num_cores=8)
        cls.test_infer_opam_deps_project = ProjectRepo(
            test_path / "CompCert",
            metadata_storage=MetadataStorage.load(
                _COQ_EXAMPLES_PATH / "comp_cert_storage.yml"))
        cls.test_infer_opam_deps_project.git.checkout(
            '7b3bc19117e48d601e392f2db2c135c7df1d8376')
        # Complete pre-req setup.
        # Use the default switch since there are no dependencies beyond
        # Coq and the package will not be installed.
        switch = OpamSwitch()
        coq_version = switch.get_installed_version("coq")
        if switch.get_installed_version("coq") is None:
            coq_version = "8.10.2"
            switch.install("coq", coq_version)
        cls.assertFalse(TestProjectSetup(), metadata.opam_repos)
        for repo in metadata.opam_repos:
            switch.add_repo(*repo.split())
        cls.assertFalse(TestProjectSetup(), metadata.opam_dependencies)
        for dep in chain(metadata.opam_dependencies):
            output = dep.split(".", maxsplit=1)
            if len(output) == 1:
                pkg = output[0]
                ver = None
            else:
                pkg, ver = output
            switch.install(pkg, ver)
        # set up test_extract_sentences
        test_path = os.path.dirname(__file__)
        repo_path = os.path.join(test_path, "circuits")
        if not os.path.exists(repo_path):
            test_repo = git.Repo.clone_from(
                "https://github.com/coq-contribs/circuits",
                repo_path)
        else:
            test_repo = git.Repo(repo_path)
        # Checkout HEAD of master as of March 14, 2022
        master_hash = "f2cec6067f2c58e280c5b460e113d738b387be15"
        test_repo.git.checkout(master_hash)
        cls.test_extract_sentences_repo_path = repo_path

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Clean up build artifacts produced as test side-effects.
        """
        for repo_path in [cls.test_iqr_project.path,
                          cls.test_infer_opam_deps_project.path]:
            shutil.rmtree(repo_path)
        shutil.rmtree(cls.test_extract_sentences_repo_path)


class TestProject(TestProjectSetup):
    """
    Test suite for Project class.
    """

    test_iqr_project: Project
    test_infer_opam_deps_project: Project

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up the class.
        """
        super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Tear down the class.
        """
        return super().tearDownClass()

    def test_extract_sentences_heuristic(self):
        """
        Test method for splitting Coq code by sentence.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=False,
                    sentence_extraction_method=SEM.HEURISTIC)
                actual_outcome = [str(s) for s in actual_outcome]
                self.assertEqual(actual_outcome, self.test_list[coq_file])

    def test_extract_sentences_heuristic_glom(self):
        """
        Test method for splitting Coq code by sentence.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=True,
                    sentence_extraction_method=SEM.HEURISTIC)
                actual_outcome = [str(s) for s in actual_outcome]
                self.assertEqual(actual_outcome, self.test_glom_list[coq_file])

    def test_extract_sentences_serapi(self):
        """
        Test method for splitting Coq code using SERAPI.
        """
        repo_path = self.test_extract_sentences_repo_path
        with pushd(repo_path):
            subprocess.run("make")
            document = CoqDocument(
                name="ADDER/Adder.v",
                project_path=repo_path,
                serapi_options=SerAPIOptions.empty(repo_path))
            with open(document.abspath, "rt") as f:
                document.source_code = f.read()
            sentences = Project.extract_sentences(
                document,
                sentence_extraction_method=SentenceExtractionMethod.SERAPI,
                glom_proofs=False)
            sentences = [str(s) for s in sentences]
            for sentence in sentences:
                self.assertTrue(
                    sentence.endswith('.') or sentence == '{' or sentence == "}"
                    or sentence.endswith("-") or sentence.endswith("+")
                    or sentence.endswith("*"))

    def test_extract_sentences_serapi_simple(self):
        """
        Test method for splitting Coq code using SERAPI.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=False,
                    sentence_extraction_method=SEM.SERAPI)
                actual_outcome = [
                    ' '.join(str(s).split()) for s in actual_outcome
                ]
                self.assertEqual(actual_outcome, self.test_list[coq_file])

    def test_extract_sentences_serapi_simple_glom(self):
        """
        Test proof glomming with serapi-based sentence extractor.
        """
        for coq_file, document in self.document.items():
            with self.subTest(coq_file):
                actual_outcome = Project.extract_sentences(
                    document,
                    glom_proofs=True,
                    sentence_extraction_method=SEM.SERAPI)
                actual_outcome = [
                    ' '.join(str(s).split()) for s in actual_outcome
                ]
                self.assertEqual(actual_outcome, self.test_glom_list[coq_file])

    def test_extract_sentences_serapi_glom_nested(self):
        """
        Test glomming with serpai-based extractor w/ nested proofs.

        This test is disabled for now until a good caching scheme can be
        developed for a built GeoCoq. However, it does pass as of
        2022-04-19.
        """
        return
        project_name = "GeoCoq"
        master_hash = "25917f56a3b46843690457b2bfd83168bed1321c"
        target_project = "GeoCoq/GeoCoq"
        test_path = os.path.dirname(__file__)
        repo_path = os.path.join(test_path, project_name)
        if not os.path.exists(repo_path):
            test_repo = git.Repo.clone_from(
                "https://github.com/" + target_project,
                repo_path)
        else:
            test_repo = git.Repo(repo_path)
        # Checkout HEAD of master as of March 14, 2022
        test_repo.git.checkout(master_hash)
        old_dir = os.path.abspath(os.curdir)
        os.chdir(repo_path)
        subprocess.run("./configure.sh")
        subprocess.run("make")
        document = CoqDocument(
            name="Tactics/Coinc/CoincR.v",
            project_path=repo_path,
            serapi_options=SerAPIOptions.empty(repo_path))
        with open(document.abspath, "rt") as f:
            document.source_code = f.read()
        actual_outcome = Project.extract_sentences(
            document,
            sentence_extraction_method=SentenceExtractionMethod.SERAPI,
            glom_proofs=True)
        actual_outcome = [str(s) for s in actual_outcome]
        for sentence in actual_outcome:
            self.assertTrue(sentence.endswith('.'))
        # Clean up
        os.chdir(old_dir)
        del test_repo
        shutil.rmtree(os.path.join(repo_path))

    def test_infer_opam_dependencies(self):
        """
        Test inferring opam dependencies from a project dir.
        """
        with self.subTest("ignore_iqr_flags"):
            expected_deps = {
                '"coq-flocq"',
                '"coq-itree"',
                '"coq-bedrock2"',
                '"coq-bedrock2-compiler"',
                '"coq-library-undecidability"',
                '"coq-menhirlib"',
                '"menhir"'
            }
            self.test_infer_opam_deps_project.infer_opam_dependencies(
                ignore_iqr_flags=True)
            deps = self.test_infer_opam_deps_project.opam_dependencies
            self.assertEqual(set(deps), expected_deps)
        with self.subTest("ignore_coq_version"):
            expected_deps = {
                '"coq-rewriter"',
                '"coq-ext-lib"',
                '"coq-containers"',
                '"menhir"'
            }
            self.test_infer_opam_deps_project.infer_opam_dependencies(
                ignore_coq_version=True)
            deps = self.test_infer_opam_deps_project.opam_dependencies
            self.assertEqual(set(deps), expected_deps)
        with self.subTest("ignore_iqr_and_coq"):
            expected_deps = {
                '"coq-flocq"',
                '"coq-itree"',
                '"coq-bedrock2"',
                '"coq-bedrock2-compiler"',
                '"coq-library-undecidability"',
                '"coq-menhirlib"',
                '"coq-rewriter"',
                '"coq-ext-lib"',
                '"coq-containers"',
                '"menhir"'
            }
            self.test_infer_opam_deps_project.infer_opam_dependencies(
                ignore_iqr_flags=True,
                ignore_coq_version=True)
            deps = self.test_infer_opam_deps_project.opam_dependencies
            self.assertEqual(set(deps), expected_deps)
        with self.subTest("standard"):
            expected_deps = {'"menhir"'}
            self.test_infer_opam_deps_project.infer_opam_dependencies()
            deps = self.test_infer_opam_deps_project.opam_dependencies
            self.assertEqual(set(deps), expected_deps)

    @pytest.mark.dependency()
    def test_build_and_get_iqr(self):
        """
        Test `Project` method builds and extracts IQR flags.
        """
        # ensure we are starting from clean slate so that strace can
        # work its magic
        self.test_iqr_project.clean()
        original_metadata = self.test_iqr_project.metadata
        output, rcode, stdout, stderr = self.test_iqr_project.infer_serapi_options()
        if not os.path.exists("./test_logs"):
            os.makedirs("./test_logs")
        with open("./test_logs/test_build_and_get_iqr.txt", "wt") as f:
            print(f"rcode = {rcode}", file=f)
            print(f"\nstdout = \n {stdout}", file=f)
            print(f"\nstderr = \n {stderr}", file=f)
        self.assertEqual(output, self.test_iqr_project.serapi_options)
        self.assertEqual(output, original_metadata.serapi_options)
        actual_result = set()
        for match in re.finditer(r"(-R|-Q|-I) [^\s]+",
                                 output.iqr.as_serapi_args()):
            actual_result.add(match.group())
        expected_result = {
            '-R vendor/array/src,Array',
            '-R src,SepLogic',
            '-R vendor/simple-classes/src,Classes',
            '-R vendor/tactical/src,Tactical'
        }
        self.assertEqual(actual_result, expected_result)
        self.assertEqual(rcode, 0)
        # build normally and compare output
        self.test_iqr_project.clean()
        _, expected_output, expected_err = self.test_iqr_project.build()
        # Test containment rather than equality because
        #   * submodules do not need to be re-initted, changing output
        #   * compilation order is not deterministic
        self.assertTrue(
            set(stdout.splitlines()).issuperset(expected_output.splitlines()))
        self.assertTrue(stderr.endswith(expected_err))

    def test_infer_serapi_options_dummy(self):
        """
        Test fast extraction of IQR flags using a dummy `coqc` wrapper.

        Show that IQR options can be extracted without performing a full
        build and that the options are considered healthy afterwards.
        """
        project = self.test_iqr_project
        project.clean()
        contexts, rcode, _, _ = project._strace_build(True, False)
        serapi_options = SerAPIOptions.merge(
            [c.serapi_options for c in contexts],
            root=project.path)
        expected_iqr_flags = IQR.parse_args(
            ' '.join(
                [
                    '-R vendor/array/src,Array',
                    '-R src,SepLogic',
                    '-R vendor/simple-classes/src,Classes',
                    '-R vendor/tactical/src,Tactical'
                ]),
            pwd=project.path)
        # assert that all glob and vo files are empty
        for dummy_artifact in chain(glob.glob(f"{project.path}/**/*.vo",
                                              recursive=True),
                                    glob.glob(f"{project.path}/**/*.glob",
                                              recursive=True)):
            with open(dummy_artifact, "r") as f:
                self.assertEqual(f.read(), "")
        self.assertEqual(serapi_options.iqr, expected_iqr_flags)
        self.assertEqual(rcode, 0)
        self.assertTrue(project._check_serapi_option_health_post_build())

    @pytest.mark.dependency(depends=["TestProject::test_build_and_get_iqr"])
    def test_get_file_dependencies(self):
        """
        Verify that interproject dependencies can be obtained.
        """
        file_deps = self.test_iqr_project.get_file_dependencies()
        expected_file_deps = {
            "src/Array.v":
                [
                    "src/Cancel.v",
                    "src/Instances.v",
                    "src/Mem.v",
                    "src/Pred.v",
                    "src/Reification/Sorting.v",
                    "src/Reification/Varmap.v",
                ],
            "src/CancelTests.v":
                [
                    'src/Cancel.v',
                    'src/Instances.v',
                    'src/Mem.v',
                    'src/Pred.v',
                    'src/Reification/Sorting.v',
                    'src/Reification/Varmap.v',
                ],
            "src/Cancel.v":
                [
                    'src/Instances.v',
                    'src/Mem.v',
                    'src/Pred.v',
                    'src/Reification/Sorting.v',
                    'src/Reification/Varmap.v',
                ],
            "src/SepLogic.v":
                [
                    'src/Cancel.v',
                    'src/Instances.v',
                    'src/Mem.v',
                    'src/Pred.v',
                    'src/Reification/Sorting.v',
                    'src/Reification/Varmap.v',
                    'src/Tactics.v'
                ],
            "src/Tactics.v":
                [
                    'src/Cancel.v',
                    'src/Instances.v',
                    'src/Mem.v',
                    'src/Pred.v',
                    'src/Reification/Sorting.v',
                    'src/Reification/Varmap.v',
                ],
            "src/TacticTests.v":
                [
                    'src/Cancel.v',
                    'src/Instances.v',
                    'src/Mem.v',
                    'src/Pred.v',
                    'src/Reification/Sorting.v',
                    'src/Reification/Varmap.v',
                    'src/Tactics.v'
                ],
            "src/Mem.v": ["src/Instances.v"],
            "src/Pred.v": ['src/Instances.v',
                           'src/Mem.v'],
            'src/PredTests.v': ['src/Instances.v',
                                'src/Mem.v',
                                'src/Pred.v'],
            "src/Instances.v": [],
            "src/Reification/Varmap.v": [],
            "src/Reification/Sorting.v": [],
        }
        self.assertEqual(file_deps, expected_file_deps)


class TestProjectBuildErrorHandling(TestProjectSetup):
    """
    Test suite for command line interface.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up the class.
        """
        super().setUpClass()

    def setUp(self) -> None:
        """
        Set up file with a failure for tests.
        """
        test_path = Path(__file__).parent
        self.repo_path = test_path / "coq-sep-logic"
        coq_sep_logic_path = self.repo_path
        self.array_path = os.path.join(coq_sep_logic_path, "src/Array.v")

        self.backup_array_path = os.path.join(
            coq_sep_logic_path,
            "src/Array_bak.not_v")
        shutil.copy(self.array_path, self.backup_array_path)

        with open(self.array_path, 'r+') as f:
            lines = f.readlines()
            # Add typo ListNotations -> ListNotattions in
            #       Import List.ListNotations.
            lines[11] = "  Import List.ListNotattions."
            f.seek(0)
            f.writelines(lines)
            f.truncate()

        lineno, bol_pos = 11, 290
        lineno_last, bol_pos_last = 11, 290
        beg_charno, end_charno = 292, 318
        self.up_to = SexpInfo.Loc(
            "src/Array.v",
            lineno,
            bol_pos,
            lineno_last,
            bol_pos_last,
            beg_charno,
            end_charno)

        return

    def tearDown(self) -> None:
        """
        Replace clean version of "Redexes.v".
        """
        shutil.copy(self.backup_array_path, self.array_path)
        return super().tearDown()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Tear down the class.
        """
        return super().tearDownClass()

    def test_instantiation_project_up_to_line(self):
        """
        Test ability to build a project up to a specific line.
        """
        metadata = ProjectMetadata.load(
            _COQ_EXAMPLES_PATH / "coq_sep_logic.yml")[0]
        storage = MetadataStorage()
        storage.insert(metadata.at_level(0))
        storage.insert(metadata)

        project = ProjectRepo(
            self.repo_path,
            storage,
            sentence_extraction_method=SEM.HEURISTIC)

        project.clean()

        command_extractor, _, _ = project.build_debug(self.up_to)
        files = os.listdir(os.path.join(self.repo_path, "src"))
        print(files)
        self.assertTrue('Mem.vo' in files)
        self.assertTrue('Pred.vo' in files)
        self.assertTrue('Cancel.vo' in files)
        self.assertIsNotNone(command_extractor)
        assert command_extractor is not None
        assert command_extractor.serapi is not None
        self.assertTrue(command_extractor.serapi.is_alive)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    unittest.main()
