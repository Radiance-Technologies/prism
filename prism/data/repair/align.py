from prism.data.document import CoqDocument
from prism.data.extract_cache import _extract_vernac_commands, extract_cache
from prism.language.gallina.parser import CoqParser
from prism.project.base import SEM, Project
from prism.project.repo import ProjectRepo
from prism.tests import _COQ_EXAMPLES_PATH, _PROJECT_EXAMPLES_PATH
from prism.util.radpytools.os import pushd
from prism.data.build_cache import VernacSentence, ProjectCommitData
from typing import List

"""
with pushd(_COQ_EXAMPLES_PATH):
    extracted_commands = _extract_vernac_commands(
        Project.extract_sentences(
            CoqDocument("Alphabet.v",
                        CoqParser.parse_source("Alphabet.v"),
                        _COQ_EXAMPLES_PATH),
                        sentence_extraction_method=SEM.HEURISTIC,
                        return_locations=True,
            glom_proofs=False),
         serapi_options="")
"""

from prism.util.alignment import lazy_align, fast_edit_distance

def normalized_string_alignment(a : str,b : str):
    cost, _ = fast_edit_distance(a,b, return_cost=True) 
    return cost/max(len(a),len(b))

def file_alignment(a: List[VernacSentence],b : List[VernacSentence]): 
    return lazy_align(range(len(a)),range(len(b)),
               lambda x,y: normalized_string_alignment(a[x].text,b[x].text),
               lambda x: 0.75)
    # the last, fixed value is a hyperparameter tradeoff between skipping and mis-matching
    # a value of 1.0 always mismatches and a value of 0.0 always skips.


def align_commits(a : ProjectCommitData, b : ProjectCommitData):
    """
    Totally untested draft function!
    Don't merge this!
    """
    # only attempt to align files present in both roots.
    alignable_files = a.command_data.keys()&b.command_data.keys()
    aligned_files = {}
    for f in alignable_files:
        a_sentences = [x.command for x in a.command_data[f]]
        b_sentences = [x.command for x in b.command_data[f]]
        aligned_files[f] = file_alignment(a_sentences,b_sentences)

    return aligned_files
