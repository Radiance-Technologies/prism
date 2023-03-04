"""
Script for performing repair instance mining.
"""
import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from prism.data.repair.mining import repair_mining_loop


def _resolve_python_objects(config: Dict[str, Any]) -> Dict[str, Any]:
    ...


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
        config_file_path = Path(__file__).parent / "mine_repair_instances.json"
    else:
        config_file_path = Path(config_file_path)
    with open(config_file_path, "r") as f:
        config = json.load(f)
    config = _resolve_python_objects(config)
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-json",
        default=None,
        help="Location of yaml configuration file for this script.")
    args = parser.parse_args()
    kwargs = load_config_json(args.config_json)
    repair_mining_loop(**kwargs)
