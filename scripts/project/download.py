"""
Clone a collection of Git repositories.
"""

from prism.project.download import multiprocess_clone

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "repos_file",
        help="The path to a file containing a list of newline separated "
        "repository URLs.")
    parser.add_argument(
        "download_directory",
        help="The directory to which each of the repositories listed in "
        "the indicated file will be cloned.")
    parser.add_argument(
        "num_workers",
        help="The number of parallel processes to use.",
        type=int,
        nargs='?',
        default=1)
    args = parser.parse_args()
    with open(args.repos_file, "r") as file:
        project_list = file.readlines()
    multiprocess_clone(project_list, args.download_directory, args.num_workers)
