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
Utility for guessing popular package versions.
"""

import glob
import re
import tempfile
import warnings
from collections import Counter
from datetime import datetime
from multiprocessing import Lock, Process
from pathlib import Path
from typing import Optional

import git

from prism.util.opam.api import OpamAPI
from prism.util.opam.formula.common import AssignedVariables
from prism.util.opam.formula.version import VersionFormula
from prism.util.opam.version import OpamVersion
from prism.util.parse import ParseError
from prism.util.radpytools import cachedmethod

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

    @cachedmethod
    @classmethod
    def search(  # noqa: C901
            cls,
            package: str,
            date: Optional[datetime] = None,
            variables: Optional[AssignedVariables] = None) -> Counter:
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

        Parameters
        ----------
        package : str
            The name of an Opam package.
        date : datetime | None
            A date/time in history at which to conduct the search.
            By default None, which defaults to "now".
        variables : AssignedVariables | None
            A map from variables to values to be used when evaluating
            version formulae, by default None.

        Returns
        -------
        Counter
            A map from each version of `package` to the number of times
            that it appeared as a dependency of other packages at the
            designated date/time in history.
        """
        # get versions in ascending order
        versions = list(
            map(
                OpamVersion.parse,
                filter(
                    lambda x: x and not x.startswith("#"),
                    OpamAPI.run(f"opam list -VA --columns=version {package}")
                    .stdout.split("\n"))))

        if date is None:
            date = datetime.now()

        with REPO_LOCK:
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
                REPO_LOCK.release()
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
            dep_regex = re.compile(
                r'depends:\s*\[\s*(?:' + cls.single_constraint_regex(False)
                + ')*(?:' + cls.single_constraint_regex(True).replace(
                    r'[^\"]+',
                    package + r"(?P<version>\.[^\"]+)?") + ')(?:'
                + cls.single_constraint_regex(False) + ')*]',
                flags=re.MULTILINE)

            count = Counter()

            for package in new_packages:
                try:
                    m = dep_regex.search(
                        (Path(str(package)) / "opam").read_text())
                except NotADirectoryError:
                    # circa 2018 some packages had different structures
                    # so we will exclude those
                    warnings.warn(f"Skipping {package}...")
                    continue
                if m is not None:
                    formula = m.group('formula')
                    version = m.group('version')
                    if formula is not None:
                        formula = formula[1 :-1].strip()
                        try:
                            constraint = VersionFormula.parse(formula)
                        except ParseError:
                            warnings.warn(
                                f"Failed to parse version formula from {formula}"
                            )
                        else:
                            simplified = constraint.simplify(
                                None,
                                variables=variables,
                                evaluate_filters=True)
                            if isinstance(simplified, VersionFormula):
                                filtered = simplified.filter_versions(
                                    versions,
                                    variables=variables)
                            elif isinstance(simplified, bool):
                                if simplified:
                                    filtered = versions
                                else:
                                    filtered = []
                            else:
                                warnings.warn(
                                    "Unsure how to filter with simplified "
                                    f"constraint '{simplified}' obtained from "
                                    f"'{constraint}'. Defaulting to True.")
                                filtered = versions
                            count.update(filtered)
                    elif version is not None:
                        version = version[1 :]
                        # version was explicitly specified.
                        try:
                            version = OpamVersion.parse(version)
                        except ParseError:
                            warnings.warn(
                                f"Failed to parse version from {version}")
                        else:
                            count[version] += 1
        return count

    @staticmethod
    def single_constraint_regex(capture: bool) -> re.Pattern:
        """
        Get a regular expression that matches a package constraint.

        Parameters
        ----------
        capture : bool
            If True, then capture the version formula in the package
            constraint as a group named ``"formula"``.

        Returns
        -------
        re.Pattern
            A regular expression that matches one package constraint.
        """
        if capture:
            capture = "?P<formula>"
        else:
            capture = "?:"
        return rf'"(?:[^\"]+)"\s*({capture}\{{[^\}}]+\}})?\s*'
