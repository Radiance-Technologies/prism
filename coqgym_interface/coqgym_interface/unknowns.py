"""
Module providing tools for dealing with unknown sequences.
"""
import re
from copy import copy
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional, Sequence, Set

from transformers import BartTokenizer, BatchEncoding, BertTokenizer


class TokenizerEnum(Enum):
    """
    Tokenizer names with preconfigured `TokenizerConfiguration`s.
    """

    BART_FACEBOOK_BART_BASE = auto()
    BERT_BASE_UNCASED = auto()
    OTHER = auto()


@dataclass
class TokenizerConfiguration:
    """
    Data-class gathering information about tokenizer configurations.

    Attributes
    ----------
    name : TokenizerEnum
        Enum form of tokenizer name
    tokenizer : Callable[[str], BatchEncoding]
        The tokenizer callable
    decode : Callable[[Sequence[int]], str]
        The callable that converts token ids to tokens
    unknown_token : str
        The string that the tokenizer uses to identify unknowns in the
        input sequence
    special_tokens : Set[str]
        A set of special tokens that the tokenizer uses for its own
        functionality, e.g., for the beginning and end of sequences
    uncased : bool
        Flag indicating whether the provided tokenizer is uncased
    """

    name: TokenizerEnum
    tokenizer: Callable[[str], BatchEncoding]
    decode: Callable[[Sequence[int]], str]
    unknown_token: str
    special_tokens: Set[str]
    uncased: bool

    @classmethod
    def from_name(cls, name: str):
        """
        Create `TokenizerConfiguration` object from tokenizer name.

        Parameters
        ----------
        name : str
            Name of tokenizer to use. Must match one of the predefined
            `TokenizerEnum` names. Case insensitive.

        Returns
        -------
        TokenizerConfiguration
            Instance of this class

        Raises
        ------
        ValueError
            If `name` does not match one of the `TokenizerEnum` enums.
        """
        if name.lower() == TokenizerEnum.BART_FACEBOOK_BART_BASE.name.lower():
            tokenizer: BartTokenizer = BartTokenizer.from_pretrained(
                "facebook/bart-base")
            return cls(
                name=TokenizerEnum.BART_FACEBOOK_BART_BASE,
                tokenizer=tokenizer,
                decode=tokenizer.decode,
                unknown_token="<unk>",
                special_tokens={"<s>",
                                "</s>",
                                "<pad>",
                                "<mask>"},
                uncased=False)
        elif name.lower() == TokenizerEnum.BERT_BASE_UNCASED.name.lower():
            tokenizer: BertTokenizer = BertTokenizer.from_pretrained(
                "bert-base-uncased")
            return cls(
                name=TokenizerEnum.BERT_BASE_UNCASED,
                tokenizer=tokenizer,
                decode=tokenizer.decode,
                unknown_token="[UNK]",
                special_tokens={'[SEP]',
                                '[PAD]',
                                '[CLS]',
                                '[MASK]'},
                uncased=True)
        else:
            raise ValueError(f"Tokenizer with name {name} is unknown.")


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


def find_and_replace_unrecognized_sequences(
        input_sequence: str,
        tokenizer_config: Optional[TokenizerConfiguration] = None) -> str:
    """
    Find/replace sequences unknown to the tokenizer.

    To find any unknown tokens in the input, the input is passed through
    the tokenizer and then decoded again using the tokenizer. If any
    `unknown_token`s are present in the reversed output, the output is
    compared to the input to find out what sequences were turned into
    `unknown_token`s.

    The reversed output is split using the `unknown_token` as a
    delimiter, and the resulting sequences are treated as "brackets"
    for the unknown sequences. These brackets are used to localize and
    identify the unknown sequences in the original input.

    Parameters
    ----------
    input_sequence : str
        The input sequence to check for unknowns
    tokenizer_config : Optional[TokenizerConfiguration], optional
        Object specifying the tokenizer configuration, None by default

    Returns
    -------
    str
        The input sequences with detected unknown tokens replaced with
        more meaningful representations
    """
    if tokenizer_config is None:
        tokenizer_config = TokenizerConfiguration.from_name(
            "bart_facebook_bart_base")
    trial_output = tokenizer_config.tokenizer(input_sequence)['input_ids']
    reversed_trial_output = tokenizer_config.decode(trial_output)
    if tokenizer_config.unknown_token in reversed_trial_output:
        unknowns: Set[str] = set()
        temp_input_sequence = copy(input_sequence)

        def _process_casing(x: str):
            if tokenizer_config.uncased:
                return x.lower()
            else:
                return x

        # Clean any non-unknown special tokens from sequences
        for token in list(tokenizer_config.special_tokens):
            temp_input_sequence = temp_input_sequence.replace(token, "")
            reversed_trial_output = reversed_trial_output.replace(token, "")
        # Strip any leading or trailing whitespace, possibly left over
        # from special tokens at the beginning or end of the sequence
        temp_input_sequence = temp_input_sequence.strip()
        reversed_trial_output = reversed_trial_output.strip()
        # Replace any remaining whitespace with single spaces to further
        # clean up after special token removal
        temp_input_sequence = re.sub(r"\s+", " ", temp_input_sequence)
        reversed_trial_output = re.sub(r"\s+", " ", reversed_trial_output)
        # Continue
        unk_token_brackets = reversed_trial_output.split(
            tokenizer_config.unknown_token)
        for start_bracket, end_bracket in zip(
                unk_token_brackets[:-1],
                unk_token_brackets[1:]):
            output_start_end_idx = _process_casing(reversed_trial_output).find(
                start_bracket) + len(start_bracket)
            input_start_end_idx = _process_casing(temp_input_sequence).find(
                start_bracket) + len(start_bracket)
            # Cut off left-hand bracket around unknown sequence
            reversed_trial_output = reversed_trial_output[
                output_start_end_idx :]
            temp_input_sequence = temp_input_sequence[input_start_end_idx :]
            # Get indices of right-hand bracket around unknown sequence
            if end_bracket:
                output_end_start_idx = _process_casing(
                    reversed_trial_output).find(end_bracket)
                input_end_start_idx = _process_casing(temp_input_sequence).find(
                    end_bracket)
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


if __name__ == "__main__":
    test_input = "foo bar ∀A bleep blorp"
    tokenizer_config = TokenizerConfiguration.from_name("bert_base_uncased")
    cleaned_output = find_and_replace_unrecognized_sequences(
        test_input,
        tokenizer_config)
    print(cleaned_output)
    print(
        tokenizer_config.decode(
            tokenizer_config.tokenizer(test_input)['input_ids']))
