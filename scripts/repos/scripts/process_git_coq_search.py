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
Extract github links to significantly Coq based projects.

This script processes repositories found by Tom Reichel here:
https://github.com/a-gardner1/coq-pearls/issues/2#issuecomment-1100753597

This text file was hand-annotated using a '*' to indicate projects
which were almost entirely Coq based. The decision to exclude
projects which had substantial non-Coq code sections was based on
the assumption that such projects would be more complex to build/rebuild
or that they would require additional prerequisites which had the
potential to balloon dev environment size or time to configure.

This script turns that information into a json file for ease of use
and manipulation in python.
"""

import json
import re

if __name__ == "__main__":

    file_in = open("./commit-then-star-sort.txt", 'r')
    lines = []

    for line in file_in:
        lines.append(line)

    regex = re.compile(r"100 (https.*)\s+\*")

    repos = []

    for line in lines:
        match = regex.match(line)
        if match:
            repos.append(match.groups()[0])

    print(repos, len(repos))
    with open("commit-then-star-sort.json", 'w') as outfile:
        json.dump(repos, outfile)
