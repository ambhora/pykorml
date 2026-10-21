# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import argparse
import pathlib

import testkorml.yamlgen as yamlgen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate korml v1 lexer functional test cases.",
    )

    subparser = parser.add_subparsers(
        dest="command",
        required=True,
    )

    single_parser = subparser.add_parser(
        "single",
        help="Generate one passing test case.",
    )
    _add_generation_arguments(single_parser)
    single_parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help=(
            "Write input.korml and expected.json to this directory. If omitted, "
            "write source to stdout."
        ),
    )

    set_parser = subparser.add_parser(
        "set",
        help="Generate a set of passing and failing test cases.",
    )
    _add_generation_arguments(set_parser)
    set_parser.add_argument("--case-count", type=int, default=100)
    set_parser.add_argument("--failure-count", type=int, default=0)
    set_parser.add_argument(
        "--feature-coverage",
        action="store_true",
        help=(
            "Generate additional cases that force each enabled feature to appear "
            "alone when possible."
        ),
    )
    set_parser.add_argument(
        "--output",
        type=pathlib.Path,
        required=True,
        help="Write numbered test-case directories below this directory.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = _config_from_args(args)

    match args.command:
        case "single":
            _main_single(args=args, config=config)

        case "set":
            _main_set(args=args, config=config)

        case _:
            raise ValueError(f"unknown generator command: {args.command}")


def _main_single(
    *,
    args: argparse.Namespace,
    config: yamlgen.GenerationConfig,
) -> None:
    case = yamlgen.generate_single_case(config)

    if args.output is None:
        print(case.source, end="")
        return

    yamlgen.write_case(
        case,
        output=args.output,
    )


def _main_set(
    *,
    args: argparse.Namespace,
    config: yamlgen.GenerationConfig,
) -> None:
    case_array = yamlgen.generate_case_set(
        config,
        case_count=args.case_count,
        failure_count=args.failure_count,
        feature_coverage=args.feature_coverage,
    )

    yamlgen.write_case_set(
        case_array,
        output=args.output,
    )


def _add_generation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--document-count", type=int, default=1)
    parser.add_argument("--version", type=str, default="1.0")

    parser.add_argument("--no-root-scalar", action="store_true")

    parser.add_argument("--no-plain-scalar", action="store_true")
    parser.add_argument("--no-single-quoted-scalar", action="store_true")
    parser.add_argument("--no-double-quoted-scalar", action="store_true")

    parser.add_argument("--no-mapping", action="store_true")
    parser.add_argument("--no-sequence", action="store_true")

    parser.add_argument("--no-flow-mapping", action="store_true")
    parser.add_argument("--no-flow-sequence", action="store_true")

    parser.add_argument("--no-literal-block-scalar", action="store_true")
    parser.add_argument("--no-folded-block-scalar", action="store_true")

    parser.add_argument("--top-level-entity-count", type=int, default=8)
    parser.add_argument("--nested-level-count", type=int, default=3)

    parser.add_argument("--max-mapping-size", type=int, default=3)
    parser.add_argument("--max-sequence-size", type=int, default=3)

    parser.add_argument("--no-document-end", action="store_true")
    parser.add_argument("--no-comments", action="store_true")
    parser.add_argument("--no-inline-comments", action="store_true")
    parser.add_argument("--no-blank-lines", action="store_true")


def _config_from_args(args: argparse.Namespace) -> yamlgen.GenerationConfig:
    _validate_positive_count("document_count", args.document_count)
    _validate_positive_count("top_level_entity_count", args.top_level_entity_count)
    _validate_nonnegative_count("nested_level_count", args.nested_level_count)
    _validate_positive_count("max_mapping_size", args.max_mapping_size)
    _validate_positive_count("max_sequence_size", args.max_sequence_size)

    config = yamlgen.GenerationConfig(
        seed=args.seed,
        document_count=args.document_count,
        version=args.version,
        root_scalar=not args.no_root_scalar,
        plain_scalar=not args.no_plain_scalar,
        single_quoted_scalar=not args.no_single_quoted_scalar,
        double_quoted_scalar=not args.no_double_quoted_scalar,
        mapping=not args.no_mapping,
        sequence=not args.no_sequence,
        flow_mapping=not args.no_flow_mapping,
        flow_sequence=not args.no_flow_sequence,
        literal_block_scalar=not args.no_literal_block_scalar,
        folded_block_scalar=not args.no_folded_block_scalar,
        top_level_entity_count=args.top_level_entity_count,
        nested_level_count=args.nested_level_count,
        max_mapping_size=args.max_mapping_size,
        max_sequence_size=args.max_sequence_size,
        document_end=not args.no_document_end,
        comments=not args.no_comments,
        inline_comments=not args.no_inline_comments,
        blank_lines=not args.no_blank_lines,
    )

    yamlgen.validate_config(config)

    return config


def _validate_nonnegative_count(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to zero")


def _validate_positive_count(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


if __name__ == "__main__":
    main()
