#!/bin/bash

if [ "$_" == "$0" ] ; then
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
  echo "Alternative versions of Coq not yet supported." && return 1
  export COQ_VERSION=$1
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
  opam switch create $OPAM_SWITCH 4.07.1 -y
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
