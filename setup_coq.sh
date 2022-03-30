#!/bin/bash

if [ "$_" == "$0" ] ; then
  echo "Please invoke as 'source $(basename $BASH_SOURCE)' instead."
  exit
fi

if [ "$1" == "" ] ; then
  echo "Defaulting to Coq version 8.10.2"
  export COQ_VERSION=8.10.2
  export SERAPI_VERSION=8.10.0+0.7.1
else
  echo "Alternative versions of Coq not yet supported." && exit 1
  export COQ_VERSION=$1
fi

if [ "$1" == "-h" ] ; then
  echo "Help: setup_coq.sh [Coq version number]"
  echo ""
  echo "Install a sandboxed version of Coq. No administrator privileges required."
fi

if [ -z ${GITROOT+x} ];
    then GITROOT=$(while :; do
                [ -d .git  ] && [ -f .prism ] && { echo `pwd`; break; };
                [ `pwd` = "/" ] && { echo ""; break; };
                cd ..;
            done);
fi

export SWITCH_NAME="prism-$COQ_VERSION"
SWITCH_DETECTED=$(opam switch list 2>&1 | grep )

# remove artifacts from previous setup
if [ ! -z ${SWITCH_DETECTED} ] ; then
  while true; do
    read -p "Previous switch of $COQ_VERSION detected. Do you want to remove and reinstall?[y/n]" yn
    case $yn in
      [Yy]* ) REINSTALL=true; break;;
      [Nn]* ) REINSTALL=false; break;;
      * ) echo "Please answer yes or no.";;
    esac
  done
fi

if [ "$REINSTALL" == "true" ] || [ "$REINSTALL" = "" ] ; then
  test ! -z ${SWITCH_DETECTED} && echo "Removing previous $COQ_VERSION switch" &&  opam switch remove $SWITCH_NAME -y

  echo "Installing requested version of Coq in switch $SWITCH_NAME"
  opam switch create $SWITCH_NAME 4.07.1 -y
	opam switch $SWITCH_NAME
  eval $(opam env)
  opam update
	opam pin add coq $COQ_VERSION
	opam pin add coq-serapi $SERAPI_VERSION
fi
