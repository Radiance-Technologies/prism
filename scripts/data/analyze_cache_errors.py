"""
Script to analyze cache extraction errors.

Use this script to display information on caching errors within a given
Coq project build cache. The project name, commit SHA, and Coq version
are printed first for each cache item with an error. A blank line
follows, and then the full contents of the error file are printed below
that. At this point, the script pauses in execution and waits for user
input. Copy any relevant details to an external file (perhaps a
spreadsheet) for further analysis, triage, and planning.

Type 'q' and then press [Enter] to stop execution early, or press
[Enter] alone to continue to the next caching error file. Once each
error file has been displayed, the number of error files processed will
be shown and the script will end.
"""
import argparse
import glob
import os

from prism.util.radpytools.os import pushd


def main(args: argparse.Namespace):
    """
    Print metadata and cache extraction error files one-by-one.

    Parameters
    ----------
    args : argparse.Namespace
        Command line argument object
    """
    counter = 0
    with pushd(args.cache_root):
        for error_file in glob.glob("**/*cache_error.txt", recursive=True):
            counter += 1
            with open(error_file, "rt") as f:
                project, commit_sha, coq_version = error_file.split(os.sep)
                coq_version = coq_version.split("_cache_error.txt")[0]
                print(f"\nProject: {project}")
                print(f"Commit sha: {commit_sha}")
                print(f"Coq version: {coq_version}")
                print("")
                print(f.read())
                cmd = input("Press q + [Enter] to quit. [Enter] to proceed.")
                if cmd.lower() == "q":
                    break
    print(f"We encountered {counter} cache error files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "cache_root",
        help="Build cache root that we want to analyze")
    args = parser.parse_args()
    main(args)
