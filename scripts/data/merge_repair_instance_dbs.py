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
        default=[],
        help='Root directories of repair instance databases',
        nargs='+')
    parser.add_argument(
        '-o',
        '--output',
        required=True,
        type=Path,
        help="The path at which the merged database should be written.")
    args = parser.parse_args()
    directories = args.directories
    if len(directories) < 2:
        parser.error("Not enough repair instance databases. Need at least two.")
    databases = [RepairInstanceDB(d) for d in directories]
    try:
        RepairInstanceDB.union(args.output, *databases)
    except Exception:
        for db in databases:
            db.__exit__(*sys.exc_info())
        raise
