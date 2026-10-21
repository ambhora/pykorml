# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Mutation fuzzing of the lexer and parser.

Each case mutates a valid source with Korml punctuation and checks two
properties that must hold for any input: loading raises nothing but a
KormlError, and lexing then unlexing gives back the source exactly.

KORML_FUZZ_SEED and KORML_FUZZ_CASES choose the seed and the number of
cases; a failure names the seed, so it can be reproduced.
"""

import os
import random

import pytest

import korml
import korml.lexer.file

_SEED = int(os.environ.get("KORML_FUZZ_SEED", "0"))
_CASES = int(os.environ.get("KORML_FUZZ_CASES", "200"))

_SEEDS = (
    "name: example\n",
    "- a\n- b\n",
    "a:\n  b: [1, 2]\n  c: {d: e}\n",
    "a: |\n  line\n  more\nb: >\n  folded\n",
    'a: \'single\' # comment\nb: "double \\" quote"\n',
    "%!korml version 1.0\n---\na: 1\n...\n---\n- x\n...\n",
)

_PIECES = (
    *" \t\n\r:-#[]{},'\"|>%!?&*\\.",
    "---",
    "...",
    "%!korml version 1.0\n",
    "\r\n",
    "  ",
    "é",
    "\x00",
    "\ufeff",
    "|-",
    "|+",
    ">2",
)


def _mutate(rng: random.Random, source: str) -> str:
    characters = list(source)
    for _ in range(rng.randint(1, 6)):
        index = rng.randint(0, len(characters))
        operation = rng.random()
        if operation < 0.4 or not characters:
            characters.insert(index, rng.choice(_PIECES))
        elif operation < 0.7:
            del characters[min(index, len(characters) - 1)]
        else:
            characters[min(index, len(characters) - 1)] = rng.choice(_PIECES)
    return "".join(characters)


@pytest.mark.parametrize("case", range(_CASES))
def test_mutated_source_fails_only_with_korml_error(case: int) -> None:
    rng = random.Random(f"{_SEED}:{case}")
    source = _mutate(rng, rng.choice(_SEEDS))

    try:
        korml.loads(source).to_builtin()
    except korml.KormlError:
        pass
    except Exception as error:
        pytest.fail(f"seed={_SEED} case={case}: {type(error).__name__} for {source!r}")

    try:
        file = korml.lexer.file.lex("<fuzz>", source)
    except korml.KormlError:
        return
    assert korml.lexer.file.unlex(file) == source, f"seed={_SEED} case={case}"
