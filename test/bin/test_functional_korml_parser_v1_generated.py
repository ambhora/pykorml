# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import random

import pytest

import korml
import korml.lexer.v1
import korml.lexer.v1.file
import korml.parser.v1
import testkorml.yamlgen


def test_generated_block_token_streams_parse() -> None:
    for seed in range(100):
        source = testkorml.yamlgen.generate_one(
            testkorml.yamlgen.GenerationConfig(
                seed=seed,
                document_count=1,
                flow_mapping=False,
                flow_sequence=False,
                document_end=True,
            )
        )

        file = korml.lexer.v1.file.lex(
            f"<generated-{seed}>",
            source,
        )

        token_array = _single_document_body_token_array(file)

        value = korml.parser.v1._parse_value(
            token_array,
            version=korml.Version.v1,
            source_name=file.filename,
        )

        assert value.version is korml.Version.v1
        assert value.token_array == token_array


def test_generated_block_token_mutations_are_handled_by_parser() -> None:
    rejected_count = 0
    accepted_count = 0

    for seed in range(100):
        source = testkorml.yamlgen.generate_one(
            testkorml.yamlgen.GenerationConfig(
                seed=seed,
                document_count=1,
                flow_mapping=False,
                flow_sequence=False,
                document_end=True,
            )
        )

        file = korml.lexer.v1.file.lex(
            f"<generated-{seed}>",
            source,
        )

        token_array = _single_document_body_token_array(file)

        mutation_array = testkorml.yamlgen.mutate_many_token_array(
            token_array,
            rng=random.Random(seed),
            mutation_count=5,
        )

        assert mutation_array

        for mutation in mutation_array:
            try:
                value = korml.parser.v1._parse_value(
                    mutation.token_array,
                    version=korml.Version.v1,
                    source_name=file.filename,
                )
            except korml.ParseError:
                rejected_count += 1
                continue

            accepted_count += 1
            assert value.version is korml.Version.v1
            assert value.token_array == tuple(mutation.token_array)

    assert rejected_count > 0
    assert accepted_count > 0


def test_token_mutation_many_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="mutation_count"):
        testkorml.yamlgen.mutate_many_token_array(
            (),
            rng=random.Random(1),
            mutation_count=-1,
        )


def test_token_mutation_all_returns_unique_mutations() -> None:
    source = "%!korml version 1.0\n---\nkey: value\n...\n"

    file = korml.lexer.v1.file.lex(
        "<test>",
        source,
    )

    token_array = _single_document_body_token_array(file)

    mutation_array = testkorml.yamlgen.mutate_all_token_array(
        token_array,
        rng=random.Random(1),
    )

    key_array = [
        tuple((token.type.name, token.value) for token in mutation.token_array)
        for mutation in mutation_array
    ]

    assert len(key_array) == len(set(key_array))


def _single_document_body_token_array(
    file: korml.lexer.v1.File,
) -> tuple[korml.lexer.v1.Token, ...]:
    start = _index_after_first_token_type(
        file.token_array,
        korml.lexer.v1.TokenType.DOC_START,
    )

    end = _index_of_first_token_type_after(
        file.token_array,
        korml.lexer.v1.TokenType.DOC_END,
        start=start,
    )

    if end is None:
        end = len(file.token_array)

    return tuple(file.token_array[start:end])


def _index_after_first_token_type(
    token_array: tuple[korml.lexer.v1.Token, ...],
    token_type: korml.lexer.v1.TokenType,
) -> int:
    for index, token in enumerate(token_array):
        if token.type is token_type:
            return index + 1

    raise AssertionError(f"missing token {token_type.name}")


def _index_of_first_token_type_after(
    token_array: tuple[korml.lexer.v1.Token, ...],
    token_type: korml.lexer.v1.TokenType,
    *,
    start: int,
) -> int | None:
    for index in range(start, len(token_array)):
        if token_array[index].type is token_type:
            return index

    return None


def test_missing_mapping_colon_token_mutation_is_rejected_by_parser() -> None:
    file = korml.lexer.v1.file.lex(
        "<test>",
        "%!korml version 1.0\n---\nkey: value\n...\n",
    )

    token_array = _single_document_body_token_array(file)

    mutation = _find_token_mutation(
        testkorml.yamlgen.mutate_all_token_array(
            token_array,
            rng=random.Random(1),
        ),
        name="missing_mapping_colon",
    )

    with pytest.raises(korml.ParseError):
        korml.parser.v1._parse_value(
            mutation.token_array,
            version=korml.Version.v1,
            source_name=file.filename,
        )


def test_missing_sequence_value_token_mutation_is_rejected_by_parser() -> None:
    file = korml.lexer.v1.file.lex(
        "<test>",
        "%!korml version 1.0\n---\n- value\n...\n",
    )

    token_array = _single_document_body_token_array(file)

    mutation = _find_token_mutation(
        testkorml.yamlgen.mutate_all_token_array(
            token_array,
            rng=random.Random(1),
        ),
        name="missing_sequence_value",
    )

    with pytest.raises(korml.ParseError):
        korml.parser.v1._parse_value(
            mutation.token_array,
            version=korml.Version.v1,
            source_name=file.filename,
        )


def _find_token_mutation(
    mutation_array: list[testkorml.yamlgen.TokenMutationResult],
    *,
    name: str,
) -> testkorml.yamlgen.TokenMutationResult:
    for mutation in mutation_array:
        if mutation.name == name:
            return mutation

    raise AssertionError(f"missing token mutation {name!r}")


def test_parse_mapping_stops_entry_after_multiline_block_scalar_sequence_item() -> None:
    source = """entity_0_0:
- - value_0
  - "double value 1"
- >
  folded line one 1


  folded line two 1
entity_0_1: |
  literal line one 1
  literal line two 1
"""

    file = korml.lexer.v1.file.lex(
        "<test>",
        f"%!korml version 1.0\n---\n{source}\n...\n",
    )

    token_array = _single_document_body_token_array(file)

    mapping = korml.parser.v1._parse_mapping(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert mapping.to_builtin() == {
        "entity_0_0": [
            ["value_0", "double value 1"],
            "folded line one 1\nfolded line two 1\n",
        ],
        "entity_0_1": "literal line one 1\nliteral line two 1\n",
    }
