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
Module for downloading projects.
"""
import os
from multiprocessing import Pool
from typing import Iterable, List, Union

from git.repo import Repo

from prism.util.radpytools import PathLike

from .util import URL, extract_name


def clone(project_url: URL, root: PathLike) -> None:
    """
    Download project to directory in a root directory.

    Also sets the repo's configuration to shared within its group owner.

    Parameters
    ----------
    project_url : ProjectUrl
        Project url.
    root : os.PathLike
        Root directory containing project folder under name of project.
    """
    project_url = project_url.strip()
    name = extract_name(project_url)
    path = os.path.join(root, name)
    if not os.path.exists(path):
        repo = Repo.clone_from(project_url, path)
    else:
        repo = Repo(path)
        # give Git permission to this user to modify config
        with repo.config_writer("global") as cw:
            cw.add_value("safe", "directory", path)
    with repo.config_writer() as cw:
        cw.set("core", "sharedRepository", "group")


def multiprocess_clone(
        project_list: List[URL],
        target: Union[PathLike,
                      Iterable[PathLike]],
        num_processes: int) -> None:
    """
    Download project in parallel.

    Parameters
    ----------
    project_list : List[ProjectUrl]
        List of projects.
    target : Union[os.PathLike, List[os.PathLike]]
        Either a common directory into which each project will be cloned
        or a per-project list of destination directories.
    num_processes : int
        Number of processes.
    """
    nprojects: int = len(project_list)
    if isinstance(target, Iterable):
        targets = list(target)
    else:
        targets = [target]
    ntargets = len(targets)
    if ntargets > 1 and len(targets) != len(project_list):
        raise ValueError(
            f"{nprojects} or 1 target expected but {ntargets} given.")
    elif ntargets == 1:
        assert not isinstance(target, Iterable)
        targets = [target for _ in project_list]

    args = ((project, target) for project, target in zip(project_list, targets))

    with Pool(num_processes) as p:
        p.map(lambda args: clone(*args), args)
