"""
Script for performing repair instance mining.
"""
import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from prism.data.repair.instance import (
    ProjectCommitDataErrorInstance,
    ProjectCommitDataRepairInstance,
)
from prism.data.repair.mining import prepare_label_pairs, repair_mining_loop


def _process_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process script config file and resolve python objects.

    For better security, don't allow resolving arbitrary callable
    imports. Restrict to those given in internal mappings.

    Parameters
    ----------
    config : Dict[str, Any]
        Config file dictionary

    Returns
    -------
    Dict[str, Any]
        Updated config file dictionary
    """
    prepare_pairs_map = {
        "prism.data.repair.mining.prepare_label_pairs": prepare_label_pairs
    }
    repair_miner_map = {
        "prism.data.repair.instance.ProjectCommitDataRepairInstance":
            ProjectCommitDataRepairInstance.make_repair_instance
    }
    changeset_miner_map = {
        "prism.data.repair.instance.ProjectCommitDataErrorInstance.default_changeset_miner":
            ProjectCommitDataErrorInstance.default_changeset_miner
    }
    if "cache_root" in config:
        config["cache_root"] = Path(config["cache_root"])
    if "repair_save_directory" in config:
        config["repair_save_directory"] = Path(config["repair_save_directory"])
    if "prepare_pairs" in config:
        config["prepare_pairs"] = prepare_pairs_map.get(
            config["prepare_pairs"],
            None)
    if "repair_miner" in config:
        config["repair_miner"] = repair_miner_map.get(
            config["repair_miner"],
            None)
    if "changeset_miner" in config:
        config["changeset_miner"] = changeset_miner_map.get(
            config["changeset_miner"],
            None)
    return config


def load_config_json(config_file_path: Optional[str]) -> Dict[str, Any]:
    """
    Load script config file from provided JSON file.

    Parameters
    ----------
    config_file_path : Optional[str]
        JSON config file to load config from

    Returns
    -------
    Dict[str, Any]
        Arguments for repair_mining_loop with any Python object args
        resolved to their actual Python objects.
    """
    if config_file_path is None:
        config_file_path = Path(
            __file__).parent / "mine_repair_instances_default_config.json"
    else:
        config_file_path = Path(config_file_path)
    with open(config_file_path, "r") as f:
        config = _process_config(json.load(f))
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-json",
        default=None,
        help="Location of json configuration file for this script.")
    args = parser.parse_args()
    kwargs = load_config_json(args.config_json)
    repair_mining_loop(**kwargs)
