#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Update math-comp metadata build and install commands.
"""
from pathlib import Path

from prism.project.metadata.storage import MetadataStorage

if __name__ == "__main__":
    module_location = Path(__file__).parent
    mds_file = (module_location.parents[1] / "dataset") / "agg_coq_repos.yml"
    mds = MetadataStorage.load(mds_file)
    new_build_cmd = ["make -C mathcomp all"]
    new_install_cmd = new_build_cmd + ["make -C mathcomp install"]
    new_clean_cmd = ["make -C mathcomp clean"]
    for record in mds.get_all("math-comp", True):
        print(record.build_cmd)
        print(record.install_cmd)
        print(record.clean_cmd)
    mds.update_all(
        "math-comp",
        build_cmd=new_build_cmd,
        install_cmd=new_install_cmd,
        clean_cmd=new_clean_cmd)
    for record in mds.get_all("math-comp", True):
        print(record.build_cmd)
        print(record.install_cmd)
        print(record.clean_cmd)
    MetadataStorage.dump(mds, mds_file)
