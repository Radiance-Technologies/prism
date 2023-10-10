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

if [ "${BASH_SOURCE[0]}" == "$0" ] ; then
  echo "Please invoke as 'source $(basename $BASH_SOURCE)' instead."
  exit
fi

HELP="Usage: setup_coq.sh [Coq version number] [-n|-y]

Install a sandboxed version of Coq. No administrator privileges required.
[-n|-y]    Do (-y) or do not (-n) overwrite existing switches.
-h         Display this message."

if [ "$1" == "-h" ] ; then
  echo -e "$HELP" && return 0
fi

if [ "$1" == "" ] || [ "$1" == "-n" ] || [ "$1" == "-y" ] ; then
  echo "Defaulting to Coq version 8.10.2"
  export COQ_VERSION=8.10.2
  export SERAPI_VERSION=8.10.0+0.7.1
  if [ "$1" == "-n" ] ; then
    REINSTALL=false
  elif [ "$1" == "-y" ] ; then
    REINSTALL=true
  fi
else
  case $1 in
    "8.9.1")
      export COQ_VERSION=8.9.1
      export SERAPI_VERSION=8.9.0+0.6.1
      ;;
    "8.10.2")
      export COQ_VERSION=8.10.2
      export SERAPI_VERSION=8.10.0+0.7.2
      ;;
    "8.11.2")
      export COQ_VERSION=8.11.2
      export SERAPI_VERSION=8.11.0+0.11.1
      ;;
    "8.12.2")
      export COQ_VERSION=8.12.2
      export SERAPI_VERSION=8.12.0+0.12.1
      ;;
    "8.13.2")
      export COQ_VERSION=8.13.2
      export SERAPI_VERSION=8.13.0+0.13.1
      ;;
    "8.14.1")
      export COQ_VERSION=8.14.1
      export SERAPI_VERSION=8.14.0+0.14.0
      ;;
    "8.15.2")
      export COQ_VERSION=8.15.2
      export SERAPI_VERSION=8.15.0+0.15.4
      ;;
    *)
      echo "${1} is not a supported version of Coq." && return 1
  esac
  echo "Using Coq version ${COQ_VERSION} and SerAPI version ${SERAPI_VERSION}."
fi

if [ ! -z ${2+x} ] ; then
  if [ "$REINSTALL" == "" ] ; then
    if [ "$2" == "-n" ] ; then
      REINSTALL=false
    elif [ "$2" == "-y" ] ; then
      REINSTALL=true
    fi
  else
    echo -e "$HELP" && return 1
  fi
fi

if [ -z ${GITROOT+x} ];
    echo "Setting GITROOT environment variable."
    then GITROOT=$(while :; do
                [ -d .git  ] && [ -f .prism ] && { echo `pwd`; break; };
                [ `pwd` = "/" ] && { echo ""; break; };
                cd ..;
            done);
fi

OPAM_SWITCH="prism-$COQ_VERSION"
echo "Checking if switch exists..."
SWITCH_DETECTED=$((opam switch list || true) | (grep $OPAM_SWITCH || true))

# remove artifacts from previous setup
if [ ! "$SWITCH_DETECTED" == "" ] ; then
  echo "Previous switch $OPAM_SWITCH with Coq==$COQ_VERSION detected. "
  if [ "$REINSTALL" == "" ] ; then
    while true; do
      read -p "Do you want to remove and reinstall?[y/n]" yn
      case $yn in
        [Yy]* ) REINSTALL=true; break;;
        [Nn]* ) REINSTALL=false; break;;
        * ) echo "Please answer yes or no.";;
      esac
    done
  fi
else
  echo "No existing switch named $OPAM_SWITCH detected."
  REINSTALL=""
fi

if [ "$REINSTALL" == "true" ] || [ "$REINSTALL" = "" ] ; then
  test "$REINSTALL" == "true" && echo "Removing $OPAM_SWITCH" && opam switch remove $OPAM_SWITCH -y

  echo "Installing requested version of Coq in switch $OPAM_SWITCH"
  opam switch create $OPAM_SWITCH 4.09.1 -y
  opam switch $OPAM_SWITCH
  echo "Updating shell environment"
  eval $(opam env --switch=$OPAM_SWITCH --set-switch)
  opam update
  opam pin add coq $COQ_VERSION -y
  opam pin add coq-serapi $SERAPI_VERSION -y
else
  opam switch $OPAM_SWITCH
  echo "Updating shell environment"
  eval $(opam env --switch=$OPAM_SWITCH --set-switch)
fi

# clean up environment
unset REINSTALL
unset OPAM_SWITCH
unset SWITCH_DETECTED
