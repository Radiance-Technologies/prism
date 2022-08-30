"""
Utility for guessing popular package versions.
"""

import glob
import re
import tempfile
from collections import Counter
from datetime import datetime
from multiprocessing import Lock, Process
from pathlib import Path

import git

from prism.util.opam.api import OpamAPI
from prism.util.opam.formula.version import VersionFormula
from prism.util.opam.version import OpamVersion
from prism.util.parse import ParseError

REPO_URL = "https://github.com/coq/opam-coq-archive.git"

# storage for the opam repos,
# cleaned up when process ends
REPO_DIRECTORY = tempfile.TemporaryDirectory()

# git can't handle being run in multiple threads on the same repo
# we also don't want to start fussing with the repo before
REPO_LOCK = Lock()
# start locked and unlock once the repo is cloned
REPO_LOCK.acquire()

# on import, grab the repository.
# but seeing as this is IO bound there's no need to block CPU on this.
# using multiprocessing to background it so programs importing this
# are snappier.


def __background_clone():
    git.Repo.clone_from(url=REPO_URL, to_path=REPO_DIRECTORY.name)
    REPO_LOCK.release()


CLONE_PROCESS = Process(target=__background_clone)
CLONE_PROCESS.start()


class VersionDistribution:
    """
    Class for information about the usage of versions of packages.
    """

    @classmethod
    def search(cls, package, date=None):
        """
        Order versions of `package` by 'popularity'.

        Returns a count of how often each version of `package` could be
        used as a dependency for the latest version of other packages.

        `date` is a datetime object specifying at what point in history
        to find the version distribution of `package`.

        Can be used as a sort key to prioritize versions of packages:
        ```
        sort(versions,
             key=lambda x: VersionDistribution.search(package)[x],
             reverse=True
        )
        ```
        where indexing an unknown value will return 0.
        """
        versions = list(
            map(
                OpamVersion.parse,
                filter(
                    lambda x: x and not x.startswith("#"),
                    OpamAPI.run(f"opam list -VA --columns=version {package}")
                    .stdout.split("\n"))))

        if date is None:
            date = datetime.now()

        REPO_LOCK.acquire()

        repo = git.Repo(REPO_DIRECTORY.name)

        # get the commit right before the time desired
        commit = repo.git.execute(
            [
                "git",
                "rev-list",
                "-n1",
                f"--before=\"{date.strftime('%Y-%m-%d')}\"",
                "master"
            ])
        if (commit == ""):
            # time given must predate entire repository!
            raise ValueError("time given predates opam-coq repo")

        repo.git.checkout(commit)

        # base directory of all packages (released,extra-dev,etc)
        all_packages = list(
            map(
                Path,
                glob.glob(
                    REPO_DIRECTORY.name + "/**/packages/*",
                    recursive=True)))

        # we only care about the most recent version
        # of packages at this timestamp
        new_packages = filter(
            None,
            (
                max(
                    map(OpamVersion.parse,
                        glob.glob(str(x / "*"))),
                    default=None) for x in all_packages))

        # build a regex to find our version constraint
        single_dep_regex = r'"[^\"]+"\s*(\{[^\}]+\})?\s*'

        dep_regex = re.compile(
            r'depends:\s*\[\s*(' + single_dep_regex + ')*('
            + single_dep_regex.replace(r'[^\"]+',
                                       package) + ')(' + single_dep_regex
            + ')*]',
            flags=re.MULTILINE)

        count = Counter()

        for package in new_packages:
            try:
                m = dep_regex.search((Path(str(package)) / "opam").read_text())
            except NotADirectoryError:
                # circa 2018 some packages had different structures
                # so we will exclude those
                continue
            if (m and m.group(4)):
                try:
                    constraint = VersionFormula.parse(m.group(4)[1 :-1])
                    count.update(constraint.filter(versions))
                except ParseError as e:
                    print(e)
                    pass

        REPO_LOCK.release()

        return count
