"""
Module for downloading projects
"""
from multiprocessing.sharedctypes import Value
import os
import json
from multiprocessing import Pool


from prism.project.repo import ProjectRepo
from prism.project.base import SEM
from prism.language.heuristic.util import ParserUtils


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
        sentences = ProjectRepo.extract_sentences(document,
                                                  glom_proofs=False,
                                                  sentence_extraction_method=project.sentence_extraction_method)
        stats = parser._compute_sentence_statistics(sentences)
        count += len(stats.ender_indices)
    return os.path.basename(path), count


def sentences(path: os.PathLike):
    """
    Count number of sentences
    """
    project = ProjectRepo(path, sentence_extraction_method=SEM.HEURISTIC)
    file_list = project.get_file_list()
    count: int = 0
    for file in file_list:
        document = project.get_file(file)
        sentences = ProjectRepo.extract_sentences(document,
                                                  glom_proofs=False,
                                                  sentence_extraction_method=project.sentence_extraction_method)
        count += len(sentences)
    return os.path.basename(path), count


if __name__ == '__main__':
    import sys
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
    with Pool(int(n_procs)) as p:
        counts = p.map(proofs, dirs)
    counts = dict(counts)
    with open(json_file, 'w') as fp:
        json.dump(counts, fp)
