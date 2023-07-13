"""
Merge repair instance databases specified as directories.
"""
import argparse
import sys
from pathlib import Path

from prism.data.repair.mining import RepairInstanceDB

if __name__ == "__main__":
    parser = argparse.ArgumentParser(Path(__file__).stem, description=__doc__)
    parser.add_argument(
        '-d',
        '--directories',
        action='append',
        default=[],
        help='Root directories of repair instance databases')
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        help="The path at which the merged database should be written.")
    args = parser.parse_args()
    directories = args.directories
    if len(directories) < 2:
        parser.error("Not enough repair instance databases. Need at least two.")
    databases = [RepairInstanceDB(d) for d in directories]
    try:
        RepairInstanceDB.union(args.output,)
    except Exception:
        for db in databases:
            db.__exit__(*sys.exc_info())
