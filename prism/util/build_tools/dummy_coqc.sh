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

DEBUG=false

if $DEBUG; then
    echo "DUMMY ARGS: $@"
fi

FALLBACK() {
    PATH=$OPAM_SWITCH_PREFIX/bin:$PATH coqc $@
    exit $?
}

# Parse arguments for the Coq file and build artifacts
for last; do
    if [[ $last == *".v" ]]; then
        TARGET=$last
    elif [[ $last == *".vo" ]] && [ ! -z ${O_ARG+x} ]; then
        VO_FILE=$last
        unset O_ARG
    elif [[ $last == "-o" ]]; then
        O_ARG=$last
    fi
done

if $DEBUG; then
    echo "TARGET: $TARGET"
    echo "VO_FILE: $VO_FILE"
    echo "O_ARG: $O_ARG"
fi

if [ -z ${TARGET+x} ] || [ ! -f $TARGET ]; then
    # no target Coq file given or the target does not exist
    if $DEBUG; then
        echo "Unable to find target"
    fi
    FALLBACK $@
elif [ ! -z ${O_ARG+x} ]; then
    # malformed argument
    if $DEBUG; then
        echo "Malformed -o arg"
    fi
    FALLBACK $@
fi

if [ -z ${VO_FILE+x} ]; then
    # no target output file given
    if $DEBUG; then
        echo "No target output given. Basing vo and glob on Coq file"
    fi
    VO_FILE="${TARGET%.v}.vo"
    GLOB_FILE="${TARGET%.v}.glob"
else
    if $DEBUG; then
        echo "Basing glob file on given target output"
    fi
    GLOB_FILE="${VO_FILE%.vo}.glob"
fi

# create fake build artifacts
if $DEBUG; then
    echo "Creating fake build artifacts"
fi
touch $VO_FILE &&
touch $GLOB_FILE ||
(
    if $DEBUG; then
        echo "Unable to create files"
    fi
    FALLBACK $@
)
