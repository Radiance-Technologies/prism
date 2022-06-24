"""
Calculate some statistics from project metadata.

This script is provided as-is and is not guaranteed to function without
adaptation to your environment.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import yaml
from packaging import version
from yaml.loader import SafeLoader

from prism.project.metadata.dataclass import ProjectMetadata
from prism.project.metadata.storage import MetadataStorage


def get_data_yaml():
    """
    Get all projects' metadata.
    """
    with open("./dataset/agg_coq_repos.yml", "r") as f:
        data = yaml.load(f, Loader=SafeLoader)
    return data


def get_proofs_sentences():
    """
    Get precomputed per-project sentence counts.
    """
    with open("./stats/proof_sentence_counts.json", "r") as f:
        data = json.load(f)
    return data


def investigate_big_agg():  # noqa: C901
    """
    Analyze the project metadata.
    """
    data = get_data_yaml()
    proofs = get_proofs_sentences()

    for datum in data:
        proj_name = datum['project_name']
        try:
            datum['proofs'] = proofs[proj_name]['proofs']
            datum['sentences'] = proofs[proj_name]['sentences']
        except Exception:
            print("Project proof access failed: ", proj_name)
        if proj_name == "coq-fcsl-pcm" or proj_name is None:
            datum['proofs'] = 0
            datum['sentences'] = 0
        if datum['coq_version'] is None:
            datum['coq_version'] = "8.10.2"
            print("Coq version is None: ", datum['project_name'])

    print("---------------------------")

    for datum in data:
        if datum['commit_sha'] is None:
            print(
                "Commit SHA is None: ",
                datum['project_name'],
                datum['project_url'],
                datum['coq_version'])

    print("---------------------------")
    data_copy = data.copy()
    for datum in data_copy:
        try:
            if version.parse(datum['coq_version']) < version.parse('8.7.0'):
                data.remove(datum)
                print(
                    "Reject due to coq version being too old: ",
                    datum['project_name'],
                    datum['coq_version'])
        except Exception as e:
            print(datum['project_name'], e.args)

    print("---------------------------")

    # print(data[0]['coq_version'])
    counts = {}
    proof_counts = {}
    sentence_counts = {}
    coq_versions = {x['coq_version'] for x in data}
    new_data = []
    for x in data:
        try:
            new_data.append((x['coq_version'], x['proofs'], x['sentences']))
        except KeyError:
            print("Could not access proofs for: ", x['project_name'])
    new_data_stripped = [x[0] for x in new_data]

    for ver in coq_versions:
        proof_counts[version.parse(ver)] = sum(
            [x['proofs'] for x in data if x['coq_version'] == ver])
        sentence_counts[version.parse(ver)] = sum(
            [x['sentences'] for x in data if x['coq_version'] == ver])

    for datum in new_data:
        counts[version.parse(datum[0])] = new_data_stripped.count(datum[0])

    sorted_version = list(reversed(sorted(counts.items())))
    print(list(proof_counts.items())[: 10])
    sorted_version_proofs = list(reversed(sorted(proof_counts.items())))
    sorted_version_sentences = list(reversed(sorted(sentence_counts.items())))
    sorted_plain = [(str(x[0]), x[1]) for x in sorted_version]
    sorted_plain_proofs = [(str(x[0]), x[1]) for x in sorted_version_proofs]
    sorted_plain_sentences = [
        (str(x[0]),
         x[1]) for x in sorted_version_sentences
    ]
    print(sorted_plain)
    # sorted_plain.remove(('8.10.2', 136))
    # sorted_plain = [('8.15.1', 11), ('8.14.1', 3), ('8.14.0', 1), ('8.13.2', 5), ('8.13.1', 1), ('8.13.0', 2), ('8.12.2', 2), ('8.12.1', 7), ('8.11.2', 4), ('8.11.1', 1), ('8.9.1', 7), ('8.8.2', 5), ('8.8.1', 2), ('8.7.1', 1)]  # noqa: W505, B950

    generate_repo_count_fig(sorted_plain)
    generate_proof_count_fig(sorted_plain_proofs)
    generate_sentence_count_fig(sorted_plain_sentences)


def generate_sentence_count_fig(sorted_plain_sentences):
    """
    Make a figure showing sentence share across projects by Coq version.
    """
    vals = [x[1] for x in sorted_plain_sentences]
    labels = [x[0] for x in sorted_plain_sentences]

    fig, ax = plt.subplots()
    # ax = fig.add_axes([0,0,1,1])
    # plt.pie(vals, labels=labels)
    # points = list(range(len(vals)))
    ax.bar(labels, vals)
    # ax.set_yticks()
    ax.set_title("Share of Sentences by Coq Version")
    # ax.set_yscale('log')
    ax.set_xlabel("Coq Versions")
    ax.set_ylabel("Number of sentences")
    plt.setp(ax.get_xticklabels(), fontsize=10, rotation='vertical')
    # ax.margins(0.6)
    plt.subplots_adjust(bottom=0.15)
    plt.savefig("./bar_chart_sentences.png")
    plt.clf()


def generate_proof_count_fig(sorted_plain_proofs):
    """
    Make a figure showing proof share across projects by Coq version.
    """
    vals = [x[1] for x in sorted_plain_proofs]
    labels = [x[0] for x in sorted_plain_proofs]

    fig, ax = plt.subplots()
    # ax = fig.add_axes([0,0,1,1])
    # plt.pie(vals, labels=labels)
    # points = list(range(len(vals)))
    ax.bar(labels, vals)
    # ax.set_yticks()
    ax.set_title("Share of Proofs by Coq Version")
    # ax.set_yscale('log')
    ax.set_xlabel("Coq Versions")
    ax.set_ylabel("Number of proofs")
    plt.setp(ax.get_xticklabels(), fontsize=10, rotation='vertical')
    # ax.margins(0.6)
    plt.subplots_adjust(bottom=0.15)
    plt.savefig("./bar_chart_proofs.png")
    plt.clf()


def generate_repo_count_fig(sorted_plain):
    """
    Make a figure Coq version share across projects.
    """
    vals = [x[1] for x in sorted_plain]
    labels = [x[0] for x in sorted_plain]

    fig, ax = plt.subplots()
    # ax = fig.add_axes([0,0,1,1])
    # plt.pie(vals, labels=labels)
    # points = list(range(len(vals)))
    ax.bar(labels, vals)
    # ax.set_yticks()
    ax.set_title("Share of Repos by Coq Version")
    # ax.set_yscale('log')
    ax.set_xlabel("Coq Versions")
    ax.set_ylabel("Number of repos")
    plt.setp(ax.get_xticklabels(), fontsize=10, rotation='vertical')
    # ax.margins(0.6)
    plt.subplots_adjust(bottom=0.15)
    plt.savefig("./bar_chart_repos.png")
    plt.clf()


def test_load_metadata():
    """
    Verify that the aggregated metadata can be loaded and dumped.
    """
    path = Path("./dataset/agg_coq_repos.yml")

    metadata = ProjectMetadata.load(path)
    # print(metadata)
    storage = MetadataStorage()
    for meta in metadata:
        storage.insert(meta)
        try:
            storage.insert(meta.at_level(0))
        except KeyError:
            print("Duplicate: ", meta.project_name)

        # print(storage)
        # print(meta.at_level(0))
        # print("--------------------------------------------------------")
    storage.dump(storage, output_filepath="./agg_coq_repos.yml")


if __name__ == "__main__":
    # investigate_big_agg()
    test_load_metadata()
