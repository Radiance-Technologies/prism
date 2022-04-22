import json
import re


if __name__ == "__main__":

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

