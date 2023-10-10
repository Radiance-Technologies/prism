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
Script to collect files specific to error messages.
"""
import argparse
import glob
import os
import re
import shutil
import tempfile
from typing import Dict, List
from zipfile import ZipFile

import pandas as pd

parser = argparse.ArgumentParser("Error finding args")

parser.add_argument("error", type=str)
parser.add_argument("--output", type=str, default="./")
parser.add_argument("--root", type=str, default="./")


def basename_pattern(misc_build_or_cache: str) -> str:
    """
    Pattern that can be used to search for specific error files.
    """
    return f'*_{misc_build_or_cache}_error.txt'


def get_file_coq_version(filename: str) -> str:
    """
    Determine coq version from error file basename.
    """
    return '.'.join(os.path.basename(filename).split('_')[0 : 3])


def find_files(root, misc_build_or_cache) -> Dict[str, List[str]]:
    """
    Find all misc, build, xor cache error files in `root`.
    """
    pattern = os.path.join(
        root,
        '*',
        '*',
        basename_pattern(misc_build_or_cache))
    files = {}
    for file in glob.glob(pattern):
        coq_version: str = get_file_coq_version(file)
        coq_version_files = files.setdefault(coq_version, [])
        coq_version_files.append(file)
    return files


def find_all_files(root) -> Dict[str, Dict[str, List[str]]]:
    """
    Find all error files in `root`.
    """
    files = {}
    files['misc'] = find_files(root, 'misc')
    files['build'] = find_files(root, 'build')
    files['cache'] = find_files(root, 'cache')
    return files


def search(error: str, files: Dict[str, Dict[str, List[str]]]):
    """
    Find all files containing the error message.
    """
    results = {}
    csv = {
        'Project': [],
        'Commit': [],
        'Coq Version': [],
        'Error Type': [],
        'Path': [],
        'Message': [],
    }
    for file_type, files_ in files.items():
        file_type_results = {}
        for coq_version, files__ in files_.items():
            coq_version_results = []
            for filename in files__:
                for line in open(filename, "r"):
                    if re.search(error, line):
                        file_type_results = results.setdefault(
                            file_type,
                            file_type_results)
                        coq_version_results = file_type_results.setdefault(
                            coq_version,
                            coq_version_results)
                        coq_version_results.append(filename)
                        csv['Project'].append(
                            os.path.basename(
                                os.path.dirname(os.path.dirname(filename))))
                        csv['Commit'].append(
                            os.path.basename(os.path.dirname(filename)))
                        csv['Coq Version'].append(coq_version)
                        csv['Error Type'].append(file_type)
                        csv['Path'].append(filename)
                        csv['Message'].append(error)
    df = pd.DataFrame(csv)
    return df.drop_duplicates()


def main() -> None:
    """
    Create zip files for each error message.
    """
    args = parser.parse_args()
    root = args.root
    error = args.error
    output_dir = args.output
    if error.split('.')[-1] == 'csv':

        def split(line):
            parts = line.split(",")
            label = parts.pop(-1)
            message = ','.join(parts)
            return message, label

    else:

        def split(line: str):
            parts = line.split(" ")
            label = parts.pop(-1)
            message = " ".join(parts)
            return message, label

    with open(error, "r") as error_list_file:
        for line in error_list_file:
            message, label = split(line)
            label = label.strip()
            files = find_all_files(root)
            csv = search(message, files)
            if not os.path.exists(output_dir):
                os.mkdir(output_dir)
            zipfile = ZipFile(
                os.path.join(output_dir,
                             f"{label}.zip"),
                mode='a')
            unique = set()
            with tempfile.TemporaryDirectory() as tmpdirname:
                added_files = set()
                csv_path = os.path.join(tmpdirname, f"{label}.csv")
                csv.to_csv(csv_path)
                zipfile.write(csv_path)
                added_files.add(csv_path)
                for _, row in csv.iterrows():
                    path = row['Path']
                    project = row['Project']
                    commit = row['Commit']
                    base = os.path.basename(path)
                    copied_base_name = f"{project}_{row['Commit']}_{base}"
                    new_path: str = os.path.join(tmpdirname, copied_base_name)
                    shutil.copy(path, new_path)
                    zipfile.write(new_path)
                    added_files.add(new_path)
                    unique.add((project, commit))
                zipfile.close()
            print(
                f"{label}: Number of unique (project, commit) pairs: {len(unique)}"
            )


if __name__ == "__main__":
    main()
