"""
Utilities module for CoqGym interface.
"""
import random
import re
from typing import List, Optional, Union

from git import Blob, Commit, Repo


class Project(Repo):
    """
    Class for representing a Coq project.

    Based on GitPython's `Repo` class.
    """

    def get_random_commit(self) -> Commit:
        """
        Return a random `Commit` object from the project repo.

        Returns
        -------
        Commit
            A random `Commit` object from the project repo
        """
        # The `Commit` objects may be large, so don't persist them
        # in the object itself.
        commits = list(self.iter_commits('--all'))
        result = random.choice(commits)
        return result

    def get_random_file(self, commit_name: Optional[str] = None) -> Blob:
        """
        Return a random Coq source file from the repo.

        The commit may be specified or left to be chosen at radnom.

        Parameters
        ----------
        commit_name : str or None
            A commit hash, branch name, or tag name indicating where
            the file should be selected from. If None, commit is chosen
            at random.

        Returns
        -------
        Blob
            A random Coq source file in the form of a Blob
        """
        if commit_name is None:
            commit_name = self.get_random_commit()
        commit = self.commit(commit_name)
        # This should traverse the tree to get all files at all levels
        files = commit.tree.traverse()

        def _select_coq_files(x: Blob) -> bool:
            if x.abspath.endswith(".v"):
                return True
            else:
                return False

        files = list(filter(_select_coq_files, files))
        result = random.choice(files)
        return result

    def get_file(self, filename: str, commit_name: str = 'master') -> Blob:
        """
        Return a specific Coq source file from a specific commit.

        Parameters
        ----------
        filename : str
            The path to the file to return.
        commit_name : str
            A commit hash, branch name, or tag name from which to fetch
            the file. This is 'master' by default.

        Returns
        -------
        Blob
            A Blob corresponding to the selected Coq source file
        """
        pass

    @staticmethod
    def _decode_byte_stream(byte_stream: bytes, encoding: str = 'utf-8') -> str:
        return byte_stream.decode(encoding)

    @staticmethod
    def _strip_comments(
            file_contents: Union[str,
                                 bytes],
            encoding: str = 'utf-8') -> str:
        comment_pattern = r"[(]+\*.*?\*[)]+"
        if isinstance(file_contents, bytes):
            file_contents = Project._decode_byte_stream(file_contents, encoding)
        str_no_comments = re.sub(comment_pattern, '', file_contents)
        return str_no_comments

    @staticmethod
    def _split_by_sentence(
            file_contents: Union[str,
                                 bytes],
            encoding: str = 'utf-8') -> List[str]:
        if isinstance(file_contents, bytes):
            file_contents = Project._decode_byte_stream(file_contents, encoding)
        file_contents_no_comments = Project._strip_comments(
            file_contents,
            encoding)
        return file_contents_no_comments.replace("\n", " ").split('.')


def main():
    """
    Test module functionality.
    """
    repo_folder = "../data/CompCert"
    compcert_repo = Project(repo_folder)
    random_file = compcert_repo.get_random_file()
    ds = random_file.data_stream
    output = ds.read()
    for line in Project._decode_byte_stream(output).split('\n'):
        print(line)
    print('*************************************')
    split_contents = Project._split_by_sentence(output)
    for line in split_contents:
        print(line)


if __name__ == "__main__":
    main()
