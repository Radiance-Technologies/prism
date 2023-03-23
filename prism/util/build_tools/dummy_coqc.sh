#!/bin/bash

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
