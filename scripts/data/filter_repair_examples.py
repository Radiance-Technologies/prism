"""
Filter repair examples in a given directory according to tags.

Repair examples are identified as ``.git.json`` files by recursively
scanning the given directory. The name of each filtered example will be
returned on a new line. Instead, one may optionally count the number of
filtered examples.
"""

import argparse
import os
import sys
import textwrap
import typing
from contextlib import contextmanager
from functools import partial
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Final, Generator, TextIO

import tqdm
from seutil import io
from tqdm.contrib.concurrent import process_map

# for faster deserialization
import prism.util.io  # noqa: F401
from prism.util.path import with_suffixes
from prism.util.radpytools import unzip
from prism.util.radpytools.path import PathLike

REPAIR_SUFFIX: Final[list[str]] = ['.git', '.json']
UNCOMPRESSED_REPAIR_SUFFIX: Final[list[str]] = ['.json']
COMPRESSED_REPAIR_SUFFIX: Final[list[str]] = ['.json', '.gz']
INDENT = ' ' * 4


@contextmanager
def fopen(
        filename: PathLike | None) -> Generator[TextIO | TextIOWrapper,
                                                None,
                                                None]:
    """
    Open a file or stdout for writing.
    """
    f: TextIO | TextIOWrapper
    if filename is not None:
        f = open(filename, mode='w')
    else:
        f = sys.stdout
    try:
        yield f
    finally:
        if f is not sys.stdout:
            f.close()


def get_diffs(filepath: Path, example: dict) -> tuple[str, str]:
    """
    Get the diffs representing the error and repair.
    """
    full_filepath = with_suffixes(filepath, UNCOMPRESSED_REPAIR_SUFFIX)
    error_diff = example['error']['change']['diff']['text']
    if isinstance(example['repaired_state_or_diff'],
                  dict) and 'diff' in example['repaired_state_or_diff']:
        repair_diff = example['repaired_state_or_diff']['diff']['text']
    elif full_filepath.exists() or with_suffixes(
            full_filepath,
            COMPRESSED_REPAIR_SUFFIX).exists():
        from prism.data.repair.instance import ProjectCommitDataRepairInstance
        full_example = ProjectCommitDataRepairInstance.load(full_filepath)
        repair_diff = full_example.repaired_git_diff.text
    else:
        repair_diff = (
            "Repair reconstruction from commit "
            "SHA not implemented")
    return error_diff, repair_diff


def filter_repair_instance_file(
        tags_filter: set[str],
        verbose: bool,
        filepath: Path) -> tuple[bool,
                                 str | None,
                                 str | None]:
    """
    Filter a repair instance file.

    Parameters
    ----------
    tags_filter : set of str
        A set of tags.
    verbose : bool
        Whether to return the formatted diffs that show the error and
        repair.
    filepath : Path
        The path to a Git-based repair instance file.

    Returns
    -------
    passes_filter : bool
        True if at least one tag in the filter is used by the repair
        instance, False otherwise.
    diff : str | None
        A formatted message containing the error and repair diffs or
        None if `verbose` is False.
    tags : set[str] | None
        The set of tags associated with the instance or None if
        `verbose` is False.
    """
    passes_filter = False
    diff = None
    example = None
    tags = None
    formatted_tags = None
    if tags_filter:
        # Avoid overhead of GitRepairInstance
        # deserialization
        example = typing.cast(dict[str, Any], io.load(filepath))
        tags = set(example['error']['tags'])
        if tags.intersection(tags_filter):
            passes_filter = True
    else:
        passes_filter = True
    if passes_filter and verbose:
        if example is None:
            example = typing.cast(dict[str, Any], io.load(filepath))
        if tags is None:
            tags = set(example['error']['tags'])
        error_diff, repair_diff = get_diffs(filepath, example)
        diff = '\n'.join(
            [
                "Introduction of error:",
                textwrap.indent(error_diff,
                                INDENT),
                "Application of repair:",
                textwrap.indent(repair_diff,
                                INDENT)
            ])
        formatted_tags = '\n'.join(
            ["Tags:",
             textwrap.indent('\n'.join(tags),
                             INDENT)])
    return passes_filter, diff, formatted_tags


if __name__ == '__main__':
    parser = argparse.ArgumentParser(Path(__file__).stem, description=__doc__)
    parser.add_argument(
        'directory',
        type=Path,
        help='A directory containing a repair dataset.')
    parser.add_argument(
        '-t',
        '--tags',
        default=[],
        help='Tag(s) by which examples will be filtered according to an exact match.',
        nargs='+')
    parser.add_argument(
        '-c',
        '--count',
        default=False,
        action='store_true',
        help='Count the number of filtered examples. Silences other output.')
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        default=False,
        help='Print the Git diff for each filtered example')
    parser.add_argument(
        '-n',
        '--nworkers',
        type=int,
        default=1,
        help='The number of processes to use to filter examples.')
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        default=None,
        help="Output results to file")
    args = parser.parse_args()

    tags_filter = set(args.tags)
    do_count: bool = args.count
    verbose: bool = args.verbose
    directory: Path = args.directory
    num_workers: int = args.nworkers
    output_file: Path | None = args.output

    candidates: list[Path] = []
    for (subdir, _, filenames) in os.walk(directory):
        for filename in tqdm.tqdm(
                filenames,
                desc=f"Scanning for repair instance files in {subdir}",
                position=1):
            filepath = Path(subdir) / filename
            if filepath.suffixes[-2 :] == REPAIR_SUFFIX:
                candidates.append(filepath)
    filter_file = partial(filter_repair_instance_file, tags_filter, verbose)
    filter_results = process_map(
        filter_file,
        candidates,
        max_workers=num_workers,
        desc="Filtering discovered repair instance files",
        chunksize=2)
    filter_results = [
        (c,
         d,
         t) for c,
        (p,
         d,
         t) in zip(candidates,
                   filter_results) if p
    ]
    if filter_results:
        (filtered_examples,
         diffs,
         tags) = typing.cast(
             tuple[list[Path],
                   list[str],
                   list[str]],
             unzip(filter_results))
    else:
        print("No repair examples match the given filters")
        exit()

    with fopen(output_file) as f:
        if do_count:
            print(len(filtered_examples), file=f)
        elif verbose:
            print(
                *[
                    '\n'.join(
                        [
                            f.name,
                            textwrap.indent(tag,
                                            INDENT),
                            textwrap.indent(diff,
                                            INDENT)
                        ]) for f,
                    diff,
                    tag in zip(filtered_examples,
                               diffs,
                               tags)
                ],
                sep='\n',
                file=f)
        else:
            print(*[f.name for f in filtered_examples], sep='\n', file=f)
