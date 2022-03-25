"""
Module providing coqgym_interface utilities.
"""
from copy import copy
from typing import Callable, Optional, Sequence, Set

from transformers import BartTokenizer, BatchEncoding


def replace_unknowns(input_sequence: str, unknown_set: Set[str]) -> str:
    """
    Replace unknowns with ascii renderings of their utf-16 encodings.

    Parameters
    ----------
    input_sequence : str
        The input sequence to replace unknowns in
    unknown_set : Set[str]
        The set of unknown characters to replace in the input sequence

    Returns
    -------
    str
        The input sequence with unknown subsequences replaced
    """
    output_sequence = input_sequence
    for unknown in list(unknown_set):
        output_sequence = output_sequence.replace(
            unknown,
            str(bytes(unknown,
                      encoding="utf-16")))
    return output_sequence


def replace_unrecognized_sequences(
        input_sequence: str,
        tokenizer: Optional[Callable[[str],
                                     BatchEncoding]] = None,
        decode: Optional[Callable[[Sequence[int]],
                                  str]] = None,
        unknown_token: str = "<unk>",
        special_tokens: Optional[Set[str]] = None) -> str:
    """
    Replace sequences unknown to tokenizer with something meaningful.

    Parameters
    ----------
    input_sequence : str
        The input sequence to check for unknowns
    tokenizer : Optional[Callable[[str], BatchEncoding]], optional
        The tokenizer callable, by default None
    decode : Optional[Callable[[Sequence[int]], str]], optional
        The callable that converts token ids to tokens, by default None
    unknown_token : str, optional
        The string that the tokenizer uses to identify unknowns in the
        input sequence, by default "<unk>"
    special_tokens : Optional[Set[str]], optional
        A set of special tokens that the tokenizer uses for its own
        functionality, e.g., for the beginning and end of sequences,
        by default None

    Returns
    -------
    str
        The input sequences with detected unknown tokens replaced with
        more meaningful representations
    """
    if tokenizer is None:
        tokenizer: BartTokenizer = BartTokenizer.from_pretrained(
            "facebook/bart-base")
    if decode is None:
        decode = tokenizer.decode
    if special_tokens is None:
        special_tokens = {"<s>",
                          "</s>",
                          "<pad>",
                          "<mask>"}
    trial_output = tokenizer(input_sequence)['input_ids']
    reversed_trial_output = decode(trial_output)
    if unknown_token in reversed_trial_output:
        unknowns: Set[str] = set()
        temp_input_sequence = copy(input_sequence)
        # Clean any non-unknown special tokens from sequences
        for token in list(special_tokens):
            temp_input_sequence = temp_input_sequence.replace(token, "")
            reversed_trial_output = reversed_trial_output.replace(token, "")
        unk_token_brackets = reversed_trial_output.split(unknown_token)
        for start_bracket, end_bracket in zip(
                unk_token_brackets[:-1],
                unk_token_brackets[1:]):
            output_start_end_idx = reversed_trial_output.find(
                start_bracket) + len(start_bracket)
            input_start_end_idx = temp_input_sequence.find(start_bracket) + len(
                start_bracket)
            # Cut off left-hand bracket around unknown sequence
            reversed_trial_output = reversed_trial_output[
                output_start_end_idx :]
            temp_input_sequence = temp_input_sequence[input_start_end_idx :]
            # Get indices of right-hand bracket around unknown sequence
            if end_bracket:
                output_end_start_idx = reversed_trial_output.find(end_bracket)
                input_end_start_idx = temp_input_sequence.find(end_bracket)
            else:
                # ...unless the end_bracket is empty, in which case, the
                # "end bracket" is the end of the string
                output_end_start_idx = None
                input_end_start_idx = None
            # Extract the unknown sequence
            unknowns.add(temp_input_sequence[0 : input_end_start_idx])
            # Cut off unknown sequence
            reversed_trial_output = reversed_trial_output[
                output_end_start_idx :]
            temp_input_sequence = temp_input_sequence[input_end_start_idx :]
        cleaned_sequence = replace_unknowns(input_sequence, unknowns)
        return cleaned_sequence
    else:
        return input_sequence
