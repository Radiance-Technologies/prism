"""
Filter repair examples in a given directory according to tags.

Repair examples are identified as ``.git.json`` files by recursively
scanning the given directory. The name of each filtered example will be
returned on a new line. Instead, one may optionally count the number of
filtered examples.
"""

import argparse
import os
import typing
from pathlib import Path
from typing import Any, Final

from seutil import io

# for faster deserialization
import prism.util.io  # noqa: F401

REPAIR_SUFFIX: Final[list[str]] = ['.git', '.json']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(Path(__file__).stem, description=__doc__)
    parser.add_argument(
        'directory',
        type=Path,
        help='A directory containing a repair dataset.')
    parser.add_argument(
        '-t',
        '--tags',
        action='append',
        default=[],
        help='Tag(s) by which examples will be filtered according to an exact match.'
    )
    parser.add_argument(
        '-c',
        '--count',
        default=False,
        action='store_true',
        help='Count the number of filtered examples.')
    args = parser.parse_args()

    tags_filter = set(args.tags)
    do_count: bool = args.count
    directory: Path = args.directory

    filtered_examples: list[Path] = []
    for subdir, _, filenames in os.walk(directory):
        for filename in filenames:
            filepath = Path(subdir) / filename
            if filepath.suffixes[-2 :] == REPAIR_SUFFIX:
                if tags_filter:
                    # Avoid overhead of GitRepairInstance
                    # deserialization
                    example = typing.cast(dict[str, Any], io.load(filepath))
                    tags = set(example['error']['tags'])
                    if tags.intersection(tags_filter):
                        filtered_examples.append(filepath)
                else:
                    filtered_examples.append(filepath)
    if do_count:
        print(len(filtered_examples))
    else:
        print(*[f.stem for f in filtered_examples], sep='\n')
