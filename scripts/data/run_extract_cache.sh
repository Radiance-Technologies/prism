#!/bin/bash
##
## Copyright (c) 2023 Radiance Technologies, Inc.
##
## This file is part of PRISM
## (see https://github.com/orgs/Radiance-Technologies/prism).
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as
## published by the Free Software Foundation, either version 3 of the
## License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public
## License along with this program. If not, see
## <http://www.gnu.org/licenses/>.
##

# Make sure to run this script out of the coq-pearls repo directory, e.g.,
# $ cd ~/projects/PEARLS/prism/pearls
# $ ./scripts/data/run_extract_cache.sh

# Set the cache root here
# Note that the /shared/PEARLS directory can only be written to if you executing
# a command under the pearls GID, via `$ sg pearls -c "<command goes here>"`
CACHE_ROOT=/shared/PEARLS/new_cache
# Make sure default permissions are correct so group can read cache files
umask u=rwx,g=rwx,o=rx
# Run extraction under the "pearls" group so file ownership is correct
sg pearls -c "python scripts/data/extract_cache.py \\
    --cache-dir $CACHE_ROOT \\
    --extract-nprocs 64 \\
    --n-build-workers 16 \\
    --max-procs-file-level 64 \\
    --opam-projects-only \\
    --commit-iterator-march-strategy CURLICUE_NEW \\
    --max-proj-build-memory 20000000000 \\
    --max-proj-build-runtime 1800"
