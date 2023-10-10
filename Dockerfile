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
FROM python:3.11-bullseye

RUN apt update && \
    apt install -y libasound2 libgbm1 libgtk-3-0 libnss3 xvfb git opam && \
    opam init --yes --disable-sandboxing && \
    mkdir /root/setup_coq

COPY setup_coq.sh /root/setup_coq/

SHELL ["/bin/bash", "-c"]

RUN eval $(opam env) && \
    cd /root/setup_coq && \
    source setup_coq.sh 8.9.1 -n && \
    source setup_coq.sh 8.10.2 -n && \
    source setup_coq.sh 8.11.2 -n && \
    source setup_coq.sh 8.12.2 -n && \
    source setup_coq.sh 8.13.2 -n && \
    source setup_coq.sh 8.14.1 -n && \
    source setup_coq.sh 8.15.2 -n

COPY requirements.txt /var/requirements.txt

RUN cd /var && \
    pip3 install virtualenv && \
    virtualenv venv && \
    source venv/bin/activate && \
    pip install -r /var/requirements.txt
