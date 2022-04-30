"""
Module for downloading projects
"""
import os
import urllib
from typing import TypeVar, List, Union, Callable, Tuple

from git import Repo
from multiprocessing import Pool


ProjectUrl = TypeVar("ProjectUrl")


def download_from_github(url: ProjectUrl, target: os.PathLike) -> Repo:
    """
    Download repo and return instance pointing to the cloned directory.

    Parameters
    ----------
    url : ProjectUrl
        Github url for repo.
    target : os.PathLike
        Cloned directory

    Returns
    -------
    Repo
        _description_
    """
    return Repo.clone_from(url, target)


def extract_name(url: ProjectUrl) -> str:
    """
    Get project name from url.

    Parameters
    ----------
    url : ProjectUrl
        Project url.

    Returns
    -------
    str
        Project name.
    """
    return urllib.parse.urlparse(url.strip()).path


def download(
    iterable_item: Tuple[ProjectUrl, Callable[[ProjectUrl, str], None], str]
):
    """
    Download project to directory in a root directory.

    Parameters
    ----------
    project_url : ProjectUrl
        Project url.
    downloader : Callable[[ProjectUrl, str], None]
        Project downloader
    root : str
        Root directory containing project folder under name of project..
    """
    url, downloader, root = iterable_item
    url = url.strip()
    name = extract_name(url).split("/")[-1]
    path = os.path.join(root, name)
    if not os.path.exists(path):
        downloader(url, path)


def multiprocess_download(
    project_list: List[ProjectUrl],
    targets: Union[str, List[str]],
    downloader: Callable[[ProjectUrl, str], None],
    n: int
):
    """
    Download project in parallel

    Parameters
    ----------
    project_list : List[ProjectUrl]
        List of projects.
    targets : Union[str, List[str]]
        List of target directories.
    downloader : Callable[[ProjectUrl, str], None]
        Project downloader.
    n : int
        Number of processes.
    """
    nprojects: int = len(project_list)
    ntargets: int = len(targets) if isinstance(targets, list) else 1
    if ntargets > 1 and len(targets) != len(project_list):
        raise ValueError(
            f"{nprojects} or 1 target expected but {ntargets} given."
        )
    elif ntargets == 1:
        targets = [targets for _ in project_list]

    args = ((project, downloader, target) for project, target in zip(project_list, targets))

    with Pool(n) as p:
        p.map(download, args)


if __name__ == '__main__':
    import sys
    with open(sys.argv[1], "r") as file:
        project_list = file.readlines()
    multiprocess_download(project_list, sys.argv[2], download_from_github, int(sys.argv[3]))
