import json
import re


if __name__ == "__main__":
    """
    Extract repository name, link, and number of commits.

    This script processes the hand-annotated repos file 
    made by Maxwell Reeser to assist in establishing correct 
    correspondence between CoqGym's projects and their 
    publicly available github repositories. Each repository's
    name was searched on google and the repository which seemed
    to best fit that included in CoqGym was listed as the proper
    link. The number of commits for each repo was also included.

    This script turns that information into a json file of triples
    for ease of use and manipulation in python.
    """

    file_in = open("./repos", 'r')
    lines = []

    for line in file_in:
        lines.append(line)

    line_tuples = []

    for i in range(int(len(lines)/2)):
        line_tuples.append((lines[i*2],lines[i*2+1]))

    #line_triples = [(k.split("-"), y) for (k, y) in line_tuples]

    regex = re.compile(r"(.*) - (https.*)")

    line_triples = []

    for repo_tuple in line_tuples:
        match = regex.match(repo_tuple[0])
        if match:
            line_triples.append((match.groups()[0], match.groups()[1].strip("\n"), repo_tuple[1].strip("\n")))
        else:
            line_triples.append((repo_tuple[0].strip("\n"), "", repo_tuple[1].strip("\n")))
    
    print(line_triples, len(line_triples))
    out = json.dumps(line_triples)
    with open("repos.json", 'w') as outfile:
        json.dump(line_triples, outfile)

