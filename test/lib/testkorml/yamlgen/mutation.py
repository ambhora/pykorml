# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import collections.abc
import dataclasses
import random


@dataclasses.dataclass(frozen=True, slots=True)
class MutationResult:
    name: str
    source: str


Mutation = collections.abc.Callable[
    [str, random.Random],
    MutationResult | None,
]


def lexer_edge_pass_case_array() -> list[str]:
    return [
        "%!korml version 1.0\r\n---\r\nkey: value\r\n",
        "%!korml version 1.0\n---\n.dot_plain\n",
        "%!korml version 1.0\n---\n[.dot_plain]\n",
        "%!korml version 1.0\n---\n-dash_plain\n",
        "%!korml version 1.0\n---\nkey: |",
        "%!korml version 1.0\r\n---\r\nkey: |\r\n  line\r\n",
        "%!korml version 1.0\r\n---\r\nkey: |\r\n\r\n  line\r\n",
        "%!korml version 1.0\n---\nkey: | header text\n  line\n",
        "%!korml version 1.0\n---\nkey: >\n  line\n",
        "%!korml version 1.0\r\n---\r\nkey: >\r\n  line\r\n",
        "%!korml version 1.0\r\n---\r\nkey: >\r\n\r\n  line\r\n",
        "%!korml version 1.0\n---\nkey: > header text\n  line\n",
    ]


def lexer_edge_fail_case_array() -> list[MutationResult]:
    return [
        MutationResult(
            name="empty_source_missing_version_directive",
            source="",
        ),
        MutationResult(
            name="whitespace_only_missing_version_directive",
            source=" \t\r\n",
        ),
        MutationResult(
            name="unterminated_single_quoted_scalar_at_eof",
            source="%!korml version 1.0\n---\nkey: 'value",
        ),
        MutationResult(
            name="unterminated_double_quoted_scalar_at_eof",
            source='%!korml version 1.0\n---\nkey: "value',
        ),
        MutationResult(
            name="flow_scalar_boundary_at_eof",
            source='%!korml version 1.0\n---\n["value"',
        ),
    ]


def mutate_one(
    source: str,
    *,
    rng: random.Random,
) -> MutationResult:
    mutation_array = _mutation_array()

    rng.shuffle(mutation_array)

    for mutation in mutation_array:
        result = mutation(source, rng)

        if result is not None:
            return result

    return _remove_version_directive(source, rng)


def mutate_many(
    source: str,
    *,
    rng: random.Random,
    mutation_count: int,
) -> list[MutationResult]:
    result_array: list[MutationResult] = []
    seen_source_set: set[str] = set()

    attempt_count = 0
    max_attempt_count = mutation_count * 100

    while len(result_array) < mutation_count and attempt_count < max_attempt_count:
        attempt_count += 1

        result = mutate_one(source, rng=rng)

        if result.source in seen_source_set:
            continue

        seen_source_set.add(result.source)
        result_array.append(result)

    return result_array


def mutate_all(
    source: str,
    *,
    rng: random.Random,
) -> list[MutationResult]:
    result_array: list[MutationResult] = []
    seen_source_set: set[str] = set()

    for mutation in _mutation_array():
        result = mutation(source, rng)

        if result is None:
            continue

        if result.source in seen_source_set:
            continue

        seen_source_set.add(result.source)
        result_array.append(result)

    return result_array


def _remove_version_directive(
    source: str,
    rng: random.Random,
) -> MutationResult:
    line_array = source.splitlines(keepends=True)

    for index, line in enumerate(line_array):
        if line.startswith("%!korml version"):
            mutated = "".join(line_array[:index] + line_array[index + 1 :])

            return MutationResult(
                name="missing_version_directive",
                source=mutated,
            )

    return MutationResult(
        name="missing_version_directive",
        source=source.replace("%!korml version 1.0\n", "", 1),
    )


def _replace_with_unsupported_version(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    if "%!korml version 1.0" not in source:
        return None

    return MutationResult(
        name="unsupported_version_directive",
        source=source.replace("%!korml version 1.0", "%!korml version 2.0", 1),
    )


def _remove_document_start(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    line_array = source.splitlines(keepends=True)

    for index, line in enumerate(line_array):
        if line.strip() == "---":
            mutated = "".join(line_array[:index] + line_array[index + 1 :])

            return MutationResult(
                name="missing_document_start",
                source=mutated,
            )

    return None


def _insert_unterminated_double_quote_at_eof(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _replace_document_body(
        source,
        text='unterminated_double: "value',
        name="unterminated_double_quoted_scalar_at_eof",
    )


def _insert_unterminated_single_quote_at_eof(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _replace_document_body(
        source,
        text="unterminated_single: 'value",
        name="unterminated_single_quoted_scalar_at_eof",
    )


def _insert_unterminated_flow_sequence_at_eof(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _replace_document_body(
        source,
        text="unterminated_sequence: [one, two",
        name="unterminated_flow_sequence_at_eof",
    )


def _insert_unterminated_flow_mapping_at_eof(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _replace_document_body(
        source,
        text="unterminated_mapping: {one: two",
        name="unterminated_flow_mapping_at_eof",
    )


def _replace_document_body(
    source: str,
    *,
    text: str,
    name: str,
) -> MutationResult | None:
    insert_offset = _find_after_document_start(source)

    if insert_offset is None:
        return None

    return MutationResult(
        name=name,
        source=source[:insert_offset] + text,
    )


def _insert_unexpected_document_start(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="---\n",
        name="unexpected_document_start",
    )


def _insert_unexpected_flow_sequence_end(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="]\n",
        name="unexpected_flow_sequence_end",
    )


def _insert_unexpected_flow_mapping_end(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="}\n",
        name="unexpected_flow_mapping_end",
    )


def _insert_unexpected_comma_at_value_start(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text=",\n",
        name="unexpected_comma_at_value_start",
    )


def _remove_closing_double_quote(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    quote_index_array = [index for index, char in enumerate(source) if char == '"']

    if len(quote_index_array) < 2:
        return _insert_after_document_start(
            source,
            text='unterminated_double: "value\n',
            name="unterminated_double_quoted_scalar",
        )

    closing_quote_index_array = quote_index_array[1::2]
    index = rng.choice(closing_quote_index_array)

    return MutationResult(
        name="unterminated_double_quoted_scalar",
        source=source[:index] + source[index + 1 :],
    )


def _remove_closing_single_quote(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    quote_index_array = [index for index, char in enumerate(source) if char == "'"]

    if len(quote_index_array) < 2:
        return _insert_after_document_start(
            source,
            text="unterminated_single: 'value\n",
            name="unterminated_single_quoted_scalar",
        )

    closing_quote_index_array = quote_index_array[1::2]
    index = rng.choice(closing_quote_index_array)

    return MutationResult(
        name="unterminated_single_quoted_scalar",
        source=source[:index] + source[index + 1 :],
    )


def _remove_flow_sequence_end(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    result = _remove_one_char(
        source,
        rng=rng,
        char="]",
        name="unterminated_flow_sequence",
    )

    if result is not None:
        return result

    return _insert_after_document_start(
        source,
        text="unterminated_sequence: [one, two\n",
        name="unterminated_flow_sequence",
    )


def _remove_flow_mapping_end(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    result = _remove_one_char(
        source,
        rng=rng,
        char="}",
        name="unterminated_flow_mapping",
    )

    if result is not None:
        return result

    return _insert_after_document_start(
        source,
        text="unterminated_mapping: {one: two\n",
        name="unterminated_flow_mapping",
    )


def _insert_missing_flow_separator_after_double_quote(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text='missing_double_separator: ["one" "two"]\n',
        name="missing_flow_separator_after_double_quote",
    )


def _insert_missing_flow_separator_after_single_quote(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="missing_single_separator: ['one' 'two']\n",
        name="missing_flow_separator_after_single_quote",
    )


def _insert_document_end_inside_flow(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="document_end_inside_flow: [...]\n",
        name="document_end_inside_flow",
    )


def _insert_literal_block_inside_flow(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="literal_block_inside_flow: [|]\n",
        name="literal_block_inside_flow",
    )


def _insert_folded_block_inside_flow(
    source: str,
    rng: random.Random,
) -> MutationResult | None:
    return _insert_after_document_start(
        source,
        text="folded_block_inside_flow: [>]\n",
        name="folded_block_inside_flow",
    )


def _remove_one_char(
    source: str,
    *,
    rng: random.Random,
    char: str,
    name: str,
) -> MutationResult | None:
    index_array = [index for index, current_char in enumerate(source) if current_char == char]

    if not index_array:
        return None

    index = rng.choice(index_array)

    return MutationResult(
        name=name,
        source=source[:index] + source[index + 1 :],
    )


def _insert_after_document_start(
    source: str,
    *,
    text: str,
    name: str,
) -> MutationResult | None:
    insert_offset = _find_after_document_start(source)

    if insert_offset is None:
        return None

    return MutationResult(
        name=name,
        source=source[:insert_offset] + text + source[insert_offset:],
    )


def _find_after_document_start(source: str) -> int | None:
    line_array = source.splitlines(keepends=True)

    offset = 0

    for line in line_array:
        offset += len(line)

        if line.strip() == "---":
            return offset

    return None


def _mutation_array() -> list[Mutation]:
    return [
        _remove_version_directive,
        _replace_with_unsupported_version,
        _remove_document_start,
        _insert_unexpected_document_start,
        _insert_unexpected_flow_sequence_end,
        _insert_unexpected_flow_mapping_end,
        _insert_unexpected_comma_at_value_start,
        _remove_closing_double_quote,
        _remove_closing_single_quote,
        _remove_flow_sequence_end,
        _remove_flow_mapping_end,
        _insert_unterminated_double_quote_at_eof,
        _insert_unterminated_single_quote_at_eof,
        _insert_unterminated_flow_sequence_at_eof,
        _insert_unterminated_flow_mapping_at_eof,
        _insert_missing_flow_separator_after_double_quote,
        _insert_missing_flow_separator_after_single_quote,
        _insert_document_end_inside_flow,
        _insert_literal_block_inside_flow,
        _insert_folded_block_inside_flow,
    ]
