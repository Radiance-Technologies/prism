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

if [ "$1" == "" ] ; then
  export VERSION=3.11.4
  echo "Defaulting to Python version $VERSION"
else
  export VERSION=$1
fi

if [ "$1" == "-h" ] ; then
  echo "Help: setup_python.sh [python 3 version number]"
  echo ""
  echo "Install a local version of Python 3. No administrator privileges required."
fi

if [ -z ${GITROOT+x} ];
    echo "Setting GITROOT environment variable."
    then GITROOT=$(while :; do
                [ -d .git  ] && [ -f .prism ] && { echo `pwd`; break; };
                [ `pwd` = "/" ] && { echo ""; break; };
                cd ..;
            done);
fi

export PYTHON_INSTALL_PATH=$HOME/.localpython-$VERSION
export PYTHON_NAME=Python-$VERSION
export PEARLS_PYTHON=$PYTHON_INSTALL_PATH/bin/python3
export PEARLS_PIP=$PYTHON_INSTALL_PATH/bin/pip3

# remove artifacts from previous setup
if [ -d $PYTHON_INSTALL_PATH ] ; then
  while true; do
    read -p "Previous installation of $PYTHON_NAME detected. Do you want to remove and reinstall?[y/n]" yn
    case $yn in
      [Yy]* ) REINSTALL=true; break;;
      [Nn]* ) REINSTALL=false; break;;
      * ) echo "Please answer yes or no.";;
    esac
  done
fi

if [ "$REINSTALL" == "true" ] || [ "$REINSTALL" = "" ] ; then
  test -d $PYTHON_INSTALL_PATH && echo "Removing previous $PYTHON_NAME installation" && rm -rf $PYTHON_INSTALL_PATH

  echo "Installing a local version of Python 3 in $PYTHON_INSTALL_PATH"
  mkdir $PYTHON_INSTALL_PATH
  pushd $PYTHON_INSTALL_PATH
  wget http://www.python.org/ftp/python/$VERSION/$PYTHON_NAME.tgz
  tar -zxvf $PYTHON_NAME.tgz
  pushd $PYTHON_NAME
  ./configure --prefix=$PYTHON_INSTALL_PATH --enable-optimizations
  make
  make install
  popd
  popd
fi

echo "Setting 'python' alias to 'python3'"
alias python=python3
echo "Setting 'pip' alias to 'pip3'"
alias pip=pip3
# deactivate a virtual environment if we are currently inside of one
deactivate 2>/dev/null || :
if ! [ "$(which python)" = "$PEARLS_PYTHON" ] ; then
  echo "Placing local $PYTHON_NAME as start of PATH"
  export PATH=$PYTHON_INSTALL_PATH/bin:$PATH
fi
echo "Updating local version of pip"
python -m pip install --upgrade pip
echo "Installing/updating local version of virtualenv"
python -m pip install -U virtualenv
echo "Installing/updating local version of wheel"
python -m pip install -U wheel
pushd $GITROOT
if ! [ -d venv-$VERSION ] ; then
  echo "Creating $PYTHON_NAME environment."
  virtualenv venv-$VERSION -p $PEARLS_PYTHON
fi
echo "Activating $PYTHON_NAME environment."
source $GITROOT/venv-$VERSION/bin/activate
export VENV=venv-$VERSION
touch requirements.txt
touch $GITROOT/venv-$VERSION/bin/activate
popd

unset VERSION
unset PYTHON_NAME
unset PYTHON_INSTALL_PATH
