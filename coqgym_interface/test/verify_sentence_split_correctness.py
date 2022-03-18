"""
Script to verify correctness of sentence splitting test.
"""
import json
import os
import shutil
import subprocess
from typing import List

if __name__ == "__main__":
    os.chdir("coqgym_interface/test")
    with open("split_by_sentence_expected.json", "r") as f:
        contents = json.load(f)
        assumed_correct: List[str] = contents["test_list"]
    with open("temp.v", "w") as f:
        f.write(" ".join(assumed_correct))
    with open("assumed_correct.s", "w") as f:
        subprocess.run(["sercomp", "--mode=sexp", "temp.v"], stdout=f)
    os.remove("temp.v")
    shutil.copy("split_by_sentence_test_file.v", "temp.v")
    with open("split_by_sentence_test_file.s", "w") as f:
        subprocess.run(["sercomp", "--mode=sexp", "temp.v"], stdout=f)
    with open("split_by_sentence_test_file.s", "r") as f:
        test_1 = f.read()
    with open("assumed_correct.s", "r") as f:
        test_2 = f.read()
    os.remove("split_by_sentence_test_file.s")
    os.remove("assumed_correct.s")
    os.remove("temp.v")
    assert test_1 == test_2
