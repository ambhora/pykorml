# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import collections.abc
import dataclasses
import dataclasses as dc
import random

import korml.lexer.v1


@dataclasses.dataclass(frozen=True, slots=True)
class TokenMutationResult:
    name: str
    token_array: tuple[korml.lexer.v1.Token, ...]


TokenMutation = collections.abc.Callable[
    [tuple[korml.lexer.v1.Token, ...], random.Random],
    TokenMutationResult | None,
]


_TRIVIA_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.WHITESPACE,
    korml.lexer.v1.TokenType.COMMENT,
    korml.lexer.v1.TokenType.NEWLINE,
}

_SCALAR_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.PLAIN_SCALAR,
    korml.lexer.v1.TokenType.SQ_SCALAR,
    korml.lexer.v1.TokenType.DQ_SCALAR,
    korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
    korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
}


def mutate_one(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    rng: random.Random,
) -> TokenMutationResult:
    concrete_token_array = tuple(token_array)
    mutation_array = _mutation_array()

    rng.shuffle(mutation_array)

    for mutation in mutation_array:
        result = mutation(concrete_token_array, rng)

        if result is not None:
            return result

    return _remove_first_non_trivia_token(concrete_token_array, rng)


def mutate_many(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    rng: random.Random,
    mutation_count: int,
) -> list[TokenMutationResult]:
    if mutation_count < 0:
        raise ValueError("mutation_count must be greater than or equal to zero")

    concrete_token_array = tuple(token_array)
    result_array: list[TokenMutationResult] = []
    seen_key_set: set[tuple[tuple[str, str], ...]] = set()

    attempt_count = 0
    max_attempt_count = max(1, mutation_count * 100)

    while len(result_array) < mutation_count and attempt_count < max_attempt_count:
        attempt_count += 1

        result = mutate_one(concrete_token_array, rng=rng)
        key = _token_array_key(result.token_array)

        if key in seen_key_set:
            continue

        seen_key_set.add(key)
        result_array.append(result)

    return result_array


def mutate_all(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    rng: random.Random,
) -> list[TokenMutationResult]:
    concrete_token_array = tuple(token_array)
    result_array: list[TokenMutationResult] = []
    seen_key_set: set[tuple[tuple[str, str], ...]] = set()

    for mutation in _mutation_array():
        result = mutation(concrete_token_array, rng)

        if result is None:
            continue

        key = _token_array_key(result.token_array)

        if key in seen_key_set:
            continue

        seen_key_set.add(key)
        result_array.append(result)

    return result_array


def _mutation_array() -> list[TokenMutation]:
    return [
        _remove_first_required_colon,
        _duplicate_first_required_colon,
        _replace_first_required_colon_with_dash_item,
        _remove_first_dash_item,
        _replace_first_dash_item_with_colon,
        _remove_value_after_first_colon,
        _remove_value_after_first_dash_item,
        _remove_first_scalar_token,
        _replace_first_scalar_token_with_colon,
        _swap_first_colon_with_following_scalar,
    ]


def _remove_first_required_colon(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.COLON)

    if index is None:
        return None

    return TokenMutationResult(
        name="missing_mapping_colon",
        token_array=token_array[:index] + token_array[index + 1 :],
    )


def _duplicate_first_required_colon(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.COLON)

    if index is None:
        return None

    return TokenMutationResult(
        name="duplicated_mapping_colon",
        token_array=token_array[: index + 1] + (token_array[index],) + token_array[index + 1 :],
    )


def _replace_first_required_colon_with_dash_item(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.COLON)

    if index is None:
        return None

    return TokenMutationResult(
        name="mapping_colon_replaced_with_dash_item",
        token_array=_replace_token_type(
            token_array,
            index=index,
            token_type=korml.lexer.v1.TokenType.DASH_ITEM,
        ),
    )


def _remove_first_dash_item(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.DASH_ITEM)

    if index is None:
        return None

    return TokenMutationResult(
        name="missing_sequence_dash_item",
        token_array=token_array[:index] + token_array[index + 1 :],
    )


def _replace_first_dash_item_with_colon(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.DASH_ITEM)

    if index is None:
        return None

    return TokenMutationResult(
        name="sequence_dash_item_replaced_with_colon",
        token_array=_replace_token_type(
            token_array,
            index=index,
            token_type=korml.lexer.v1.TokenType.COLON,
        ),
    )


def _remove_first_scalar_token(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_scalar_index(token_array)

    if index is None:
        return None

    return TokenMutationResult(
        name="missing_scalar_token",
        token_array=token_array[:index] + token_array[index + 1 :],
    )


def _replace_first_scalar_token_with_colon(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    index = _find_first_scalar_index(token_array)

    if index is None:
        return None

    return TokenMutationResult(
        name="scalar_token_replaced_with_colon",
        token_array=_replace_token_type(
            token_array,
            index=index,
            token_type=korml.lexer.v1.TokenType.COLON,
        ),
    )


def _remove_value_after_first_colon(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    colon_index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.COLON)

    if colon_index is None:
        return None

    value_index = _next_non_trivia_index(token_array, colon_index + 1)

    if value_index is None:
        return None

    value_end = _end_of_line_index(token_array, value_index)

    return TokenMutationResult(
        name="missing_mapping_value",
        token_array=token_array[:value_index] + token_array[value_end:],
    )


def _remove_value_after_first_dash_item(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    dash_index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.DASH_ITEM)

    if dash_index is None:
        return None

    value_index = _next_non_trivia_index(token_array, dash_index + 1)

    if value_index is None:
        return None

    value_end = _end_of_line_index(token_array, value_index)

    return TokenMutationResult(
        name="missing_sequence_value",
        token_array=token_array[:value_index] + token_array[value_end:],
    )


def _swap_first_colon_with_following_scalar(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult | None:
    colon_index = _find_first_token_index(token_array, korml.lexer.v1.TokenType.COLON)

    if colon_index is None:
        return None

    scalar_index = _next_non_trivia_index(token_array, colon_index + 1)

    if scalar_index is None:
        return None

    if token_array[scalar_index].type not in _SCALAR_TOKEN_TYPE_SET:
        return None

    mutable_token_array = list(token_array)
    mutable_token_array[colon_index], mutable_token_array[scalar_index] = (
        mutable_token_array[scalar_index],
        mutable_token_array[colon_index],
    )

    return TokenMutationResult(
        name="mapping_colon_swapped_with_value",
        token_array=tuple(mutable_token_array),
    )


def _remove_first_non_trivia_token(
    token_array: tuple[korml.lexer.v1.Token, ...],
    rng: random.Random,
) -> TokenMutationResult:
    index = _next_non_trivia_index(token_array, 0)

    if index is None:
        return TokenMutationResult(
            name="empty_token_array",
            token_array=(),
        )

    return TokenMutationResult(
        name="missing_first_non_trivia_token",
        token_array=token_array[:index] + token_array[index + 1 :],
    )


def _replace_token_type(
    token_array: tuple[korml.lexer.v1.Token, ...],
    *,
    index: int,
    token_type: korml.lexer.v1.TokenType,
) -> tuple[korml.lexer.v1.Token, ...]:
    token = token_array[index]

    replacement = dc.replace(
        token,
        type=token_type,
    )

    return token_array[:index] + (replacement,) + token_array[index + 1 :]


def _find_first_token_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    token_type: korml.lexer.v1.TokenType,
) -> int | None:
    for index, token in enumerate(token_array):
        if token.type is token_type:
            return index

    return None


def _find_first_scalar_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> int | None:
    for index, token in enumerate(token_array):
        if token.type in _SCALAR_TOKEN_TYPE_SET:
            return index

    return None


def _next_non_trivia_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    start: int,
) -> int | None:
    index = start

    while index < len(token_array):
        if token_array[index].type not in _TRIVIA_TOKEN_TYPE_SET:
            return index

        index += 1

    return None


def _end_of_line_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    start: int,
) -> int:
    index = start

    while index < len(token_array):
        if token_array[index].type is korml.lexer.v1.TokenType.NEWLINE:
            return index

        index += 1

    return len(token_array)


def _token_array_key(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> tuple[tuple[str, str], ...]:
    return tuple((token.type.name, token.value) for token in token_array)
