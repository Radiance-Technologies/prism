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


# You do need to be logged in already to do this.
# If you aren't, do the following:

# docker login rsngit.radiancetech.com:5005

docker build -t rsngit.radiancetech.com:5005/pearls/coq-pearls .

docker push rsngit.radiancetech.com:5005/pearls/coq-pearls
