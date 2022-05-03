"""
Module for downloading projects.
"""
import json
import os
import sys
from multiprocessing import Pool

from prism.project.base import SEM
from prism.project.repo import ProjectRepo


def proofs(path: os.PathLike):
    """
    Count number proofs.
    """
    project = ProjectRepo(path, sentence_extraction_method=SEM.HEURISTIC)
    parser = project.sentence_extraction_method.parser()
    file_list = project.get_file_list()
    count: int = 0
    for file in file_list:
        document = project.get_file(file)
        sentences = ProjectRepo.extract_sentences(
            document,
            glom_proofs=False,
            sentence_extraction_method=project.sentence_extraction_method)
        stats = parser._compute_sentence_statistics(sentences)
        count += len(stats.ender_indices)
    return os.path.basename(path), count


def sentences(path: os.PathLike):
    """
    Count number of sentences.
    """
    project = ProjectRepo(path, sentence_extraction_method=SEM.HEURISTIC)
    file_list = project.get_file_list()
    count: int = 0
    for file in file_list:
        document = project.get_file(file)
        sentences = ProjectRepo.extract_sentences(
            document,
            glom_proofs=False,
            sentence_extraction_method=project.sentence_extraction_method)
        count += len(sentences)
    return os.path.basename(path), count


def all_counts(path: os.PathLike):
    """
    Generate counting for sentences and proofs.
    """
    name, p = proofs(path)
    name, s = sentences(path)
    return {
        name: {
            "proofs": p,
            "sentences": s
        }
    }


if __name__ == '__main__':

    root_dir = sys.argv[1]
    json_file = sys.argv[2]
    n_procs = sys.argv[3]
    mode = sys.argv[4]
    dirs = [os.path.join(root_dir, path) for path in os.listdir(root_dir)]

    if mode == 'proofs':
        func = proofs
    elif mode == 'sentences':
        func = sentences
    else:
        raise ValueError(f"Invalid mode: {mode}")

    counts = {}
    with Pool(int(n_procs)) as p:
        data = p.map(all_counts, dirs)
    for d in data:
        counts.update(d)

    total_proof = 0
    total_sentence = 0
    with open(json_file, 'w') as fp:
        json.dump(counts, fp)
    print(f"Total proofs: {total_proof}")
    print(f"Total sentences: {total_sentence}")
