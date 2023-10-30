#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Module to produce config file.
"""
import argparse
import json
from pathlib import Path

from git import InvalidGitRepositoryError
from git.repo import Repo

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Repair config file generation")
    parser.add_argument("cache_dir", type=str, help="Root of build cache.")
    parser.add_argument(
        "--repair_dir",
        type=str,
        default=None,
        help="Root of repair directory."
        " By default the checked out coq-pearls commit SHA")
    parser.add_argument(
        "--repo",
        type=str,
        help="Root of the coq-pearls repo."
        " By default discovered based on parent directories of this script.",
        default=None)
    parser.add_argument(
        "--metadata-yml",
        type=str,
        help="Path to metadata storage YAML file."
        " By default 'dataset/metadata.yml' in the coq-pearls repo",
        default=None)
    parser.add_argument(
        "--file",
        type=str,
        help="Output file."
        " By default 'mine_repair_instances_config.json'"
        " in the same directory as this script.",
        default=None)
    args = parser.parse_args()
    repo = args.repo
    metadata_yml = args.metadata_yml
    if repo is None:
        repo = Path(__file__).parent
    try:
        repo = Repo(path=repo)
    except InvalidGitRepositoryError:
        repo = Repo(path=repo, search_parent_directories=True)
    working_tree_dir = repo.working_tree_dir
    if working_tree_dir is None:
        raise RuntimeError("Cannot produce config from bare repository")
    working_tree_dir = Path(working_tree_dir)
    if metadata_yml is None:
        metadata_yml = str(working_tree_dir / "dataset" / "metadata.yml")
    if args.repair_dir is None:
        repair_dir = repo.commit().hexsha
    else:
        repair_dir = args.repair_dir
    file = args.file or (
        Path(__file__).parent / "mine_repair_instances_config.json")
    config = {
        "cache_root":
            args.cache_dir,
        "repair_instance_db_directory":
            f"/workspace/pearls/repairs/{repair_dir}",
        "metadata_storage_file":
            metadata_yml,
        "cache_format_extension":
            "json",
        "prepare_pairs":
            "prism.data.repair.mining.prepare_label_pairs",
        "repair_miner":
            "prism.data.repair.instance.ProjectCommitDataRepairInstance",
        "changeset_miner":
            "prism.data.repair.instance.ProjectCommitDataErrorInstance.default_changeset_miner",
        "serial":
            False,
        "max_workers":
            64,
        "logging_level":
            "DEBUG",
        "skip_errors":
            True,
        "fast":
            True
    }
    json.dump(config, open(file, "w"))
