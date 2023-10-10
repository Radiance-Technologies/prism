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
Clone a collection of Git repositories.
"""

from prism.project.download import multiprocess_clone

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "repos_file",
        help="The path to a file containing a list of newline separated "
        "repository URLs.")
    parser.add_argument(
        "download_directory",
        help="The directory to which each of the repositories listed in "
        "the indicated file will be cloned.")
    parser.add_argument(
        "num_workers",
        help="The number of parallel processes to use.",
        type=int,
        nargs='?',
        default=1)
    args = parser.parse_args()
    with open(args.repos_file, "r") as file:
        project_list = file.readlines()
    multiprocess_clone(project_list, args.download_directory, args.num_workers)
