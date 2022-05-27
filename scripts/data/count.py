"""
Count sentences and proofs contained in projects.
"""
import json
import os
from multiprocessing import Pool
from typing import Dict, Tuple

from prism.project.base import SEM
from prism.project.repo import ProjectRepo


def proofs(path: os.PathLike) -> Tuple[str, int]:
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


def sentences(path: os.PathLike) -> Tuple[str, int]:
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


def all_counts(path: os.PathLike) -> Dict[str, Dict[str, int]]:
    """
    Generate counting for sentences and proofs.
    """
    try:
        name, p = proofs(path)
        name, s = sentences(path)
        return {
            name: {
                "proofs": p,
                "sentences": s
            }
        }
    except Exception as e:
        print(f"{type(e).__name__} encountered in {path}")
        raise e


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root_dir",
        help="The root directory containing project subdirectories.")
    parser.add_argument(
        "out_file",
        help="The path to a JSON file to which results will be dumped.")
    parser.add_argument(
        "num_workers",
        help="The number of parallel processes to use.",
        type=int,
        nargs='?',
        default=1)
    args = parser.parse_args()

    dirs = [
        os.path.join(args.root_dir,
                     path) for path in os.listdir(args.root_dir)
    ]

    counts = {}
    with Pool(args.num_workers) as p:
        data = p.map(all_counts, dirs)
    for d in data:
        counts.update(d)

    total_proof = sum([d["proofs"] for d in counts.values()])
    total_sentence = sum([d["sentences"] for d in counts.values()])
    with open(args.out_file, 'w') as fp:
        json.dump(counts, fp)
    print(f"Total proofs: {total_proof}")
    print(f"Total sentences: {total_sentence}")
