import argparse
import json
from random import random, seed

import numpy as np
from prettytable import PrettyTable
from tqdm import tqdm

seed(2)
np.random.seed(2)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--count",
    default="count.json",
    help="json file produced by count.py")
parser.add_argument(
    "--crosses",
    default="crosses.json",
    help="json file produced by check-crosses")
args = parser.parse_args()

with open(args.count, "r") as f:
    counts = json.load(f)

with open(args.crosses, "r") as f:
    crosses = json.load(f)

crosses = [set(crosses[p]).union({p}) for p in crosses]

groups = {}
groups = []
all_disjoint = False
last_group = set()
for group in crosses:
    for other in crosses:
        if not group.isdisjoint(other):
            group = group.union(other)
    sym_int = last_group ^ group
    new_groups = []
    for prev in groups:
        if not group.isdisjoint(prev):
            group = group.union(prev)
        else:
            new_groups.append(prev)
    new_groups.append(group)
    groups = new_groups

for p in counts:
    if not any(p in g for g in groups):
        groups.append({p})

groups = {hash(frozenset(group)): list(group) for group in groups}

sorted_projects = sorted(counts.keys())
nprojects = len(counts)
print("Number of Projects: ", nprojects)


def proof_sum(projects):
    return sum(counts[p]['proofs'] for p in projects)


def sentence_sum(projects):
    return sum(counts[p]['sentences'] for p in projects)


combined = {}
for group in groups:
    projects = groups[group]
    combined[group] = {
        'projects': projects,
        'proofs': proof_sum(projects),
        'sentences': sentence_sum(projects),
    }

sorted_n = dict(
    sorted(combined.items(),
           key=lambda item: len(item[1]['projects'])))
sorted_p = dict(sorted(combined.items(), key=lambda item: item[1]['proofs']))
sorted_s = dict(sorted(combined.items(), key=lambda item: item[1]['sentences']))

with open("combined.json", "w") as f:
    json.dump(combined, f)
with open("combined_sort_n_projects.json", "w") as f:
    json.dump(sorted_n, f)
with open("combined_proof_count.json", "w") as f:
    json.dump(sorted_p, f)
with open("combined_sentence_count.json", "w") as f:
    json.dump(sorted_s, f)

total_projects = 0
total_proofs = 0
total_sentences = 0
lines = []
for group in combined:
    projects = len(combined[group]['projects'])
    proofs = combined[group]['proofs']
    sentences = combined[group]['sentences']
    total_projects += projects
    total_proofs += proofs
    total_sentences += sentences

pt = PrettyTable()
pt.field_names = [
    'Group Hash',
    'Project Count',
    'Project %',
    'Proof Count',
    'Proof %',
    'Sentence Count',
    'Sentence %'
]
for group in sorted_p:
    projects = len(combined[group]['projects'])
    proofs = combined[group]['proofs']
    sentences = combined[group]['sentences']
    project_percent = "%0.2f" % (projects / total_projects * 100)
    proof_percent = "%0.2f" % (proofs / total_proofs * 100)
    sentence_percent = "%0.2f" % (sentences / total_sentences * 100)
    pt.add_row(
        [
            group,
            projects,
            project_percent,
            proofs,
            proof_percent,
            sentences,
            sentence_percent
        ])

pt.add_row(
    [
        "TOTAL",
        total_projects,
        total_projects / nprojects,
        total_proofs,
        1,
        total_sentences,
        1
    ])

print(pt)


def print_project(p):
    for group in combined:
        if target_project in combined[group]['projects']:
            p, s = combined[group]['proofs'], combined[group]['sentences']
            msg = (
                f"{target_project}:\n"
                f"\tHash: {group}\n"
                f"\tProofs: {p}\n"
                f"\tSentences: {s}\n")
            print(msg)
            break

max_group = None
max_value = None
for group in combined:
    if max_value is None or combined[group]['proofs'] > max_value:
        max_value = combined[group]['proofs']
        max_group = group
max_percent = max_value / total_proofs

training_set = {
    max_group: combined.pop(max_group)
}

threshold = 0.0001
validation_set = None
closest = 100
n = int(len(combined) / 2)
while True:
    subset = np.random.choice(list(combined.keys()), n, replace=False)
    pcount = sum(combined[key]['proofs'] for key in subset)
    scount = sum(combined[key]['sentences'] for key in subset)
    ppcent = pcount / total_proofs
    spcent = scount / total_sentences
    pgoal = (1 - (.8186)) / 2
    sgoal = (1 - (.8159)) / 2
    perr = abs(ppcent - pgoal)
    serr = abs(spcent - sgoal)
    larger = max(perr, serr)
    if larger < closest:
        closest = larger
        print(closest)
    if perr < threshold and serr < threshold:
        validation_set = {key: combined.pop(key) for key in subset}
        break

test_set = combined

val = [
    project for group in validation_set.values()
    for project in group['projects']
]
test = [project for group in test_set.values() for project in group['projects']]
train = [
    project for group in training_set.values() for project in group['projects']
]

with open('split.json', 'w') as f:
    json.dump({
        'train': train,
        'validation': val,
        'test': test,
    },
              f)
