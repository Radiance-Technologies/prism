"""
Script to split single line all_repos.txt file into multiple lines.
"""
import ast
from math import ceil


if __name__ == "__main__":
    with open("repos/all_repos.txt", "rt") as f:
        repo_list_str = f.read()
    repo_list = ast.literal_eval(repo_list_str)
    repo_list = sorted(repo_list)
    with open("repos/all_repos_newline_sorted.txt", "wt") as f:
        for item in repo_list:
            f.write(item + "\n")
    user_specific_out_files = [
        "repos/wesley.txt",
        "repos/max.txt",
        "repos/juan.txt"]
    N = len(repo_list)
    boundary = int(ceil(N/3))
    for i, item in enumerate(repo_list):
        out_file = user_specific_out_files[i // boundary]
        with open(out_file, "at") as f:
            f.write(item + "\n")
