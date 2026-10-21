# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import dataclasses
import json
import pathlib
import random
import typing

import korml.lexer.v1
import korml.lexer.v1.file
import testkorml.yamlgen.core as core
import testkorml.yamlgen.mutation as mutation
import testkorml.yamlgen.tokenmutation as tokenmutation

__all__ = [
    "GeneratedCase",
    "GenerationConfig",
    "MutationResult",
    "TokenMutationResult",
    "config_from_mapping",
    "generate_one",
    "generate_many",
    "generate_single_case",
    "generate_case_set",
    "write_case",
    "write_case_set",
    "write_pass_case",
    "write_fail_case",
    "expected_token_array",
    "mutate_one_token_array",
    "mutate_many_token_array",
    "mutate_all_token_array",
    "validate_config",
]

TokenMutationResult = tokenmutation.TokenMutationResult

mutate_one_token_array = tokenmutation.mutate_one
mutate_many_token_array = tokenmutation.mutate_many
mutate_all_token_array = tokenmutation.mutate_all

GenerationConfig = core.GenerationConfig
MutationResult = mutation.MutationResult

config_from_mapping = core.config_from_mapping
generate_one = core.generate_one
generate_many = core.generate_many
validate_config = core.validate_config


@dataclasses.dataclass(frozen=True, slots=True)
class GeneratedCase:
    name: str
    source: str
    should_fail: bool = False


def generate_single_case(
    config: GenerationConfig | dict[str, typing.Any],
) -> GeneratedCase:
    if isinstance(config, dict):
        config = core.config_from_mapping(config)

    source = core.generate_one(config)

    return GeneratedCase(
        name="generated",
        source=source,
        should_fail=False,
    )


def generate_case_set(
    config: GenerationConfig | dict[str, typing.Any],
    *,
    case_count: int,
    failure_count: int = 0,
    feature_coverage: bool = False,
) -> list[GeneratedCase]:
    if case_count <= 0:
        raise ValueError("case_count must be greater than zero")

    if failure_count < 0:
        raise ValueError("failure_count must be greater than or equal to zero")

    if isinstance(config, dict):
        config = core.config_from_mapping(config)

    core.validate_config(config)

    rng = random.Random(config.seed)

    pass_source_array = _generate_unique_pass_sources(
        base_config=config,
        case_count=case_count,
        feature_coverage=feature_coverage,
        rng=rng,
    )

    fail_mutation_array = _generate_unique_fail_mutations(
        pass_source_array=pass_source_array,
        failure_count=failure_count,
        rng=rng,
    )

    case_array: list[GeneratedCase] = []

    for source in pass_source_array:
        case_array.append(
            GeneratedCase(
                name="generated",
                source=source,
                should_fail=False,
            )
        )

    for fail_mutation in fail_mutation_array:
        case_array.append(
            GeneratedCase(
                name=fail_mutation.name,
                source=fail_mutation.source,
                should_fail=True,
            )
        )

    return case_array


def write_case(
    case: GeneratedCase,
    *,
    output: pathlib.Path,
) -> None:
    if case.should_fail:
        write_fail_case(
            source=case.source,
            output=output,
            name=case.name,
        )
    else:
        write_pass_case(
            source=case.source,
            output=output,
        )


def write_case_set(
    case_array: list[GeneratedCase],
    *,
    output: pathlib.Path,
) -> None:
    output.mkdir(parents=True, exist_ok=True)

    for case_index, case in enumerate(case_array, start=1):
        if case.should_fail:
            case_path = output / f"{case_index:03d}_{case.name}.fail"
        else:
            case_path = output / f"{case_index:03d}_{case.name}"

        write_case(
            case,
            output=case_path,
        )


def write_pass_case(
    *,
    source: str,
    output: pathlib.Path,
) -> None:
    output.mkdir(parents=True, exist_ok=True)

    _write_source(
        source=source,
        output=output,
    )

    (output / "expected.json").write_text(
        json.dumps(
            expected_token_array(source),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_fail_case(
    *,
    source: str,
    output: pathlib.Path,
    name: str,
) -> None:
    output.mkdir(parents=True, exist_ok=True)

    _write_source(
        source=source,
        output=output,
    )

    try:
        korml.lexer.v1.file.lex("<generated>", source)
    except korml.LexError as error:
        error_code = error.code()
    else:
        raise RuntimeError(
            f"expected mutated {name} source to fail lexing, but it passed\nsource:\n{source}"
        )

    (output / "unexpected.error.json").write_text(
        json.dumps(
            {
                "code": error_code.value,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def expected_token_array(source: str) -> list[dict]:
    token_file = korml.lexer.v1.file.lex("<generated>", source)

    return [token.to_dict() for token in token_file.token_array]


def _write_source(
    *,
    source: str,
    output: pathlib.Path,
) -> None:
    (output / "input.korml").write_bytes(source.encode("utf-8"))


def _generate_unique_pass_sources(
    *,
    base_config: GenerationConfig,
    case_count: int,
    feature_coverage: bool,
    rng: random.Random,
) -> list[str]:
    source_array: list[str] = []
    seen_source_set: set[str] = set()

    for source in mutation.lexer_edge_pass_case_array():
        if source in seen_source_set:
            continue

        seen_source_set.add(source)
        source_array.append(source)

        if len(source_array) >= case_count:
            return source_array

    if feature_coverage:
        for config in _feature_coverage_config_array(base_config):
            source = core.generate_one(config)

            if source in seen_source_set:
                continue

            seen_source_set.add(source)
            source_array.append(source)

            if len(source_array) >= case_count:
                return source_array

    attempt_count = 0
    max_attempt_count = case_count * 1000

    while len(source_array) < case_count and attempt_count < max_attempt_count:
        attempt_count += 1

        seed = rng.randrange(0, 2**32)

        config = dataclasses.replace(
            base_config,
            seed=seed,
        )

        source = core.generate_one(config)

        if source in seen_source_set:
            continue

        seen_source_set.add(source)
        source_array.append(source)

    if len(source_array) < case_count:
        raise RuntimeError(
            f"could only generate {len(source_array)} unique passing cases "
            f"out of requested {case_count}"
        )

    return source_array


def _generate_unique_fail_mutations(
    *,
    pass_source_array: list[str],
    failure_count: int,
    rng: random.Random,
) -> list[mutation.MutationResult]:
    mutation_array: list[mutation.MutationResult] = []
    seen_source_set: set[str] = set()

    if failure_count == 0:
        return mutation_array

    for fail_mutation in mutation.lexer_edge_fail_case_array():
        if fail_mutation.source in seen_source_set:
            continue

        seen_source_set.add(fail_mutation.source)
        mutation_array.append(fail_mutation)

        if len(mutation_array) >= failure_count:
            return mutation_array

    for source in pass_source_array:
        for fail_mutation in mutation.mutate_all(source, rng=rng):
            if fail_mutation.source in seen_source_set:
                continue

            seen_source_set.add(fail_mutation.source)
            mutation_array.append(fail_mutation)

            if len(mutation_array) >= failure_count:
                return mutation_array

    attempt_count = 0
    max_attempt_count = failure_count * 1000

    while len(mutation_array) < failure_count and attempt_count < max_attempt_count:
        attempt_count += 1

        source = rng.choice(pass_source_array)
        fail_mutation = mutation.mutate_one(source, rng=rng)

        if fail_mutation.source in seen_source_set:
            continue

        seen_source_set.add(fail_mutation.source)
        mutation_array.append(fail_mutation)

    if len(mutation_array) < failure_count:
        raise RuntimeError(
            f"could only generate {len(mutation_array)} unique failing cases "
            f"out of requested {failure_count}"
        )

    return mutation_array


def _feature_coverage_config_array(
    base_config: GenerationConfig,
) -> list[GenerationConfig]:
    return [
        _config_for_single_feature(base_config=base_config, feature=feature)
        for feature in _enabled_feature_array(base_config)
    ]


def _enabled_feature_array(
    config: GenerationConfig,
) -> list[str]:
    feature_array: list[str] = []

    if config.plain_scalar:
        feature_array.append("plain_scalar")

    if config.single_quoted_scalar:
        feature_array.append("single_quoted_scalar")

    if config.double_quoted_scalar:
        feature_array.append("double_quoted_scalar")

    if config.literal_block_scalar:
        feature_array.append("literal_block_scalar")

    if config.folded_block_scalar:
        feature_array.append("folded_block_scalar")

    if config.mapping:
        feature_array.append("mapping")

    if config.sequence:
        feature_array.append("sequence")

    if config.flow_mapping:
        feature_array.append("flow_mapping")

    if config.flow_sequence:
        feature_array.append("flow_sequence")

    return feature_array


def _config_for_single_feature(
    *,
    base_config: GenerationConfig,
    feature: str,
) -> GenerationConfig:
    kwargs = {
        "plain_scalar": False,
        "single_quoted_scalar": False,
        "double_quoted_scalar": False,
        "literal_block_scalar": False,
        "folded_block_scalar": False,
        "mapping": False,
        "sequence": False,
        "flow_mapping": False,
        "flow_sequence": False,
    }

    kwargs[feature] = True

    if feature in {"mapping", "sequence", "flow_mapping", "flow_sequence"}:
        kwargs["plain_scalar"] = base_config.plain_scalar
        kwargs["single_quoted_scalar"] = base_config.single_quoted_scalar
        kwargs["double_quoted_scalar"] = base_config.double_quoted_scalar
        kwargs["literal_block_scalar"] = base_config.literal_block_scalar
        kwargs["folded_block_scalar"] = base_config.folded_block_scalar

        if not any(
            [
                kwargs["plain_scalar"],
                kwargs["single_quoted_scalar"],
                kwargs["double_quoted_scalar"],
                kwargs["literal_block_scalar"],
                kwargs["folded_block_scalar"],
            ]
        ):
            kwargs["plain_scalar"] = True

    return dataclasses.replace(
        base_config,
        root_scalar=False,
        **kwargs,
    )
