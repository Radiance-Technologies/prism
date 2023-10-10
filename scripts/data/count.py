#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Count sentences and proofs contained in projects.
"""
import json
import os
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List, Set, Tuple

from prism.project import ProjectDir
from prism.project.base import SEM
from prism.project.metadata.storage import MetadataStorage
from prism.project.util import name_variants


def ignore_roots(path: Path) -> Set[str]:
    """
    Generate list of possible path stems to ignore.

    Parameters
    ----------
    path : Path
        Directory containing all project directories.

    Returns
    -------
    Set[str]
        A list of names that should be ignored if found
        in a path.
    """
    path = Path(path)
    proj_dirs = set(next(os.walk(path.parent))[1])
    projects = proj_dirs
    projects.remove(path.stem)
    for p in iter(proj_dirs):
        projects = projects.union(name_variants(p))
    return projects


def proofs(path: os.PathLike, storage: MetadataStorage) -> Tuple[str, int]:
    """
    Count number proofs.
    """
    path = Path(path)
    ignore = ignore_roots(path)

    project = ProjectDir(
        path,
        storage,
        sentence_extraction_method=SEM.HEURISTIC)
    parser = project.sentence_extraction_method.parser()
    file_list = project.get_file_list()
    count: int = 0
    project_dirs: List[Path] = []
    for file in file_list:
        if Path(file).stem in ignore or any(Path(file).is_relative_to(p)
                                            for p in project_dirs):
            project_dirs.append(Path(file))
            continue
        document = project.get_file(file)
        sentences = ProjectDir.extract_sentences(
            document,
            glom_proofs=False,
            sentence_extraction_method=project.sentence_extraction_method)
        stats = parser._compute_sentence_statistics([s.text for s in sentences])
        count += len(stats.ender_indices)
    return os.path.basename(path), count


def sentences(path: os.PathLike, storage: MetadataStorage) -> Tuple[str, int]:
    """
    Count number of sentences.
    """
    path = Path(path)
    ignore = ignore_roots(path)

    project = ProjectDir(
        path,
        storage,
        sentence_extraction_method=SEM.HEURISTIC)
    file_list = project.get_file_list()
    count: int = 0
    project_dirs: List[Path] = []
    for file in file_list:
        if Path(file).stem in ignore or any(Path(file).is_relative_to(p)
                                            for p in project_dirs):
            project_dirs.append(Path(file))
            continue
    for file in file_list:
        document = project.get_file(file)
        sentences = ProjectDir.extract_sentences(
            document,
            glom_proofs=False,
            sentence_extraction_method=project.sentence_extraction_method)
        count += len(sentences)
    return os.path.basename(path), count


def all_counts(path: os.PathLike,
               storage: MetadataStorage) -> Dict[str,
                                                 Dict[str,
                                                      int]]:
    """
    Generate counting for sentences and proofs.
    """
    try:
        name, p = proofs(path, storage)
        name, s = sentences(path, storage)
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
    storage = MetadataStorage.load("../../dataset/agg_coq_repos.yml")

    dirs = [
        os.path.join(args.root_dir,
                     path) for path in os.listdir(args.root_dir)
    ]

    counts = {}
    with Pool(args.num_workers) as p:
        data = p.starmap(all_counts, [(d, storage) for d in dirs])
    for d in data:
        counts.update(d)

    total_proof = sum([d["proofs"] for d in counts.values()])
    total_sentence = sum([d["sentences"] for d in counts.values()])
    with open(args.out_file, 'w') as fp:
        json.dump(counts, fp)
    print(f"Total proofs: {total_proof}")
    print(f"Total sentences: {total_sentence}")
