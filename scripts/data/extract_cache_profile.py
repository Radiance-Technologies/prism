"""
Script to perform cache extraction.
"""
import argparse
import cProfile
import logging
import os
import pathlib
import tempfile
from datetime import datetime
from typing import List

import gprof2dot
import pydot

from prism.data.extract_cache import (
    CacheExtractor,
    cache_extract_commit_iterator,
)
from prism.data.setup import create_default_switches
from prism.util.swim import AutoSwitchManager

if __name__ == "__main__":
    # Get args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=str(pathlib.Path.home() / "projects" / "PEARLS"))
    args, _ = parser.parse_known_args()
    ROOT: str = args.root
    parser.add_argument(
        "--default-commits-path",
        default=f"{ROOT}/prism/pearls/dataset/default_commits.yml")
    parser.add_argument(
        "--mds-file",
        default=f"{ROOT}/prism/pearls/dataset/agg_coq_repos.yml")
    parser.add_argument("--project-root-path", default=f"{ROOT}/repos_full")
    parser.add_argument("--log-dir", default=f"{ROOT}/caching/log")
    args = parser.parse_args()
    default_commits_path: str = args.default_commits_path
    mds_file: str = args.mds_file
    project_root_path: str = args.project_root_path
    log_dir: str = args.log_dir
    os.makedirs(log_dir, exist_ok=True)
    # Fixed constants
    extract_nprocs = 1
    n_build_workers = 16
    force_serial = True
    num_switches = 7
    profile = True
    project_names = ["CompCert"]
    files_to_use = {
        "CompCert":
            {
                'MenhirLib/Alphabet.v',
                'MenhirLib/Grammar.v',
                # 'MenhirLib/Automaton.v',
                # 'MenhirLib/Validator_classes.v',
                # 'MenhirLib/Validator_safe.v',
                # 'MenhirLib/Interpreter.v',
                # 'MenhirLib/Validator_complete.v',
                # 'MenhirLib/Interpreter_complete.v',
                # 'MenhirLib/Interpreter_correct.v',
                # 'MenhirLib/Main.v',
                # 'flocq/IEEE754/SpecFloatCompat.v',
                # 'flocq/Core/Zaux.v',
                # 'flocq/Core/Raux.v',
                # 'flocq/Core/Defs.v',
                # 'flocq/Core/Digits.v',
                # 'flocq/Core/Float_prop.v',
                # 'flocq/Core/Round_pred.v',
                # 'flocq/Core/Generic_fmt.v',
                # 'flocq/Core/Ulp.v',
                # 'flocq/Core/Round_NE.v'
            }
    }
    # Force redirect the root logger to a file
    # This might break due to multiprocessing. If so, it should just
    # be disabled
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_name = f"extraction_log_{timestamp}.log"
    log_file_path = os.path.join(log_dir, log_file_name)
    logging.basicConfig(filename=log_file_path, force=True)
    # Do things
    create_default_switches(num_switches)
    swim = AutoSwitchManager()
    with tempfile.TemporaryDirectory() as cache_dir:
        cache_extractor = CacheExtractor(
            cache_dir,
            mds_file,
            swim,
            default_commits_path,
            cache_extract_commit_iterator,
            files_to_use=files_to_use)
        with cProfile.Profile() as pr:
            cache_extractor.run(
                project_root_path,
                log_dir,
                extract_nprocs=extract_nprocs,
                force_serial=force_serial,
                n_build_workers=n_build_workers,
                profile=True,
                project_names=project_names)
            dump_file_name = os.path.join(log_dir, f"profile_{timestamp}.out")
            dot_file_name = os.path.join(log_dir, f"profile_{timestamp}.dot")
            pdf_file_name = os.path.join(log_dir, f"call_graph_{timestamp}.pdf")
            pr.dump_stats(dump_file_name)
            gprof2dot.main(
                ["-f",
                 "pstats",
                 dump_file_name,
                 "-o",
                 dot_file_name])
            graphs: List[pydot.Dot] = pydot.graph_from_dot_file(dot_file_name)
            graphs[0].write_pdf(pdf_file_name)
