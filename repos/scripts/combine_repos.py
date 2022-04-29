import json
import re


if __name__ == "__main__":

    coqgym_repos = json.load(open("./repos.json", 'r'))
    other_repos = json.load(open("./commit-then-star-sort.json", 'r'))

    repos = {"coqgym": coqgym_repos, "github": other_repos}

    with open("combined.json", 'w') as outfile:
        json.dump(repos, outfile)