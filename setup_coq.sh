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
  echo -e "$HELP" && exit 0
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
  echo "Alternative versions of Coq not yet supported." && exit 1
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
    echo -e "$HELP" && exit 1
  fi
fi

if [ -z ${GITROOT+x} ];
    then GITROOT=$(while :; do
                [ -d .git  ] && [ -f .prism ] && { echo `pwd`; break; };
                [ `pwd` = "/" ] && { echo ""; break; };
                cd ..;
            done);
fi

export OPAMSWITCH="prism-$COQ_VERSION"

if [ "$REINSTALL" == "" ] ; then
  SWITCH_DETECTED=$(opam switch list 2>&1 | grep $OPAMSWITCH)

  # remove artifacts from previous setup
  if [ ! -z ${SWITCH_DETECTED+x} ] ; then
    while true; do
      read -p "Previous switch $OPAMSWITCH with Coq==$COQ_VERSION detected. Do you want to remove and reinstall?[y/n]" yn
      case $yn in
        [Yy]* ) REINSTALL=true; break;;
        [Nn]* ) REINSTALL=false; break;;
        * ) echo "Please answer yes or no.";;
      esac
    done
  fi
fi

if [ "$REINSTALL" == "true" ] || [ "$REINSTALL" = "" ] ; then
  test "$REINSTALL" == "true" && echo "Removing $OPAMSWITCH" && opam switch remove $OPAMSWITCH -y

  echo "Installing requested version of Coq in switch $OPAMSWITCH"
  opam switch create $OPAMSWITCH 4.07.1 -y
  opam switch $OPAMSWITCH
  echo "Updating shell environment"
  eval $(opam env)
  opam update
  opam pin add coq $COQ_VERSION -y
  opam pin add coq-serapi $SERAPI_VERSION -y
else
  opam switch $OPAMSWITCH
  echo "Updating shell environment"
  eval $(opam env)
fi
