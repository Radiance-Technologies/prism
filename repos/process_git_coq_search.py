import json
import re


if __name__ == "__main__":

    file_in = open("./commit-then-star-sort.txt", 'r')
    lines = []

    for line in file_in:
        lines.append(line)

    #line_triples = [(k.split("-"), y) for (k, y) in line_tuples]

    regex = re.compile(r"100 (https.*)\s+\*")

    repos = []

    for line in lines:
        match = regex.match(line)
        if match:
            repos.append(match.groups()[0])
    
    print(repos, len(repos))
    with open("commit-then-star-sort.json", 'w') as outfile:
        json.dump(repos, outfile)

