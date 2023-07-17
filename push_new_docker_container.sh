#!/bin/bash

# You do need to be logged in already to do this.
# If you aren't, do the following:

# docker login rsngit.radiancetech.com:5005

docker build -t rsngit.radiancetech.com:5005/pearls/coq-pearls:coq_deps .

docker push rsngit.radiancetech.com:5005/pearls/coq-pearls:coq_deps
