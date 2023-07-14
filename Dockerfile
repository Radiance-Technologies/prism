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
