# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import dataclasses
import io
import random
import typing

import ruamel.yaml
import ruamel.yaml.comments
import ruamel.yaml.scalarstring


@dataclasses.dataclass(frozen=True, slots=True)
class GenerationConfig:
    seed: int | None = None
    document_count: int = 1
    version: str = "1.0"

    root_scalar: bool = True

    plain_scalar: bool = True
    single_quoted_scalar: bool = True
    double_quoted_scalar: bool = True

    mapping: bool = True
    sequence: bool = True

    flow_mapping: bool = True
    flow_sequence: bool = True

    literal_block_scalar: bool = True
    folded_block_scalar: bool = True

    top_level_entity_count: int = 8
    nested_level_count: int = 3

    max_mapping_size: int = 3
    max_sequence_size: int = 3

    document_end: bool = True

    comments: bool = True
    inline_comments: bool = True
    blank_lines: bool = True


def config_from_mapping(mapping: dict[str, typing.Any]) -> GenerationConfig:
    return GenerationConfig(**mapping)


def validate_config(config: GenerationConfig) -> None:
    scalar_enabled = (
        config.plain_scalar or config.single_quoted_scalar or config.double_quoted_scalar
    )

    block_scalar_enabled = config.literal_block_scalar or config.folded_block_scalar

    collection_enabled = (
        config.mapping or config.sequence or config.flow_mapping or config.flow_sequence
    )

    leaf_enabled = scalar_enabled or block_scalar_enabled

    if not leaf_enabled and not collection_enabled:
        raise ValueError("at least one node kind must be enabled")

    if config.root_scalar and not scalar_enabled:
        raise ValueError("root_scalar requires at least one scalar kind to be enabled")

    if collection_enabled and not leaf_enabled:
        raise ValueError("at least one scalar or block scalar kind must be enabled as a leaf node")


def generate_one(config: GenerationConfig | dict[str, typing.Any]) -> str:
    if isinstance(config, dict):
        config = config_from_mapping(config)

    validate_config(config)

    rng = random.Random(config.seed)

    return _generate_source(config, rng)


def generate_many(
    config: GenerationConfig | dict[str, typing.Any],
    *,
    case_count: int,
) -> list[str]:
    if isinstance(config, dict):
        config = config_from_mapping(config)

    validate_config(config)

    rng = random.Random(config.seed)

    return [_generate_source(config, rng) for _ in range(case_count)]


def _generate_source(config: GenerationConfig, rng: random.Random) -> str:
    document_array: list[str] = []

    for document_index in range(config.document_count):
        document_array.append(
            _generate_document(
                document_index=document_index,
                config=config,
                rng=rng,
            )
        )

    return "\n".join(document_array) + "\n"


def _generate_document(
    *,
    document_index: int,
    config: GenerationConfig,
    rng: random.Random,
) -> str:
    model = _generate_document_model(
        document_index=document_index,
        config=config,
        rng=rng,
    )

    if isinstance(model, str):
        body = model + "\n"
    else:
        body = _dump_model(model)

    body = _decorate_body(body, config=config, rng=rng)

    line_array = [
        f"%!korml version {config.version}",
        "---",
        body.rstrip(),
    ]

    if config.document_end:
        line_array.append("...")

    return "\n".join(line_array)


def _generate_document_model(
    *,
    document_index: int,
    config: GenerationConfig,
    rng: random.Random,
) -> typing.Any:
    if config.root_scalar and config.top_level_entity_count == 1:
        return _generate_scalar(
            index=document_index,
            scalar_kind=_choose_scalar_kind(config=config, rng=rng),
        )

    document = ruamel.yaml.comments.CommentedMap()

    for entity_index in range(config.top_level_entity_count):
        document[f"entity_{document_index}_{entity_index}"] = _generate_node(
            index=entity_index,
            depth=0,
            config=config,
            rng=rng,
        )

    document.fa.set_block_style()

    return document


def _generate_node(
    *,
    index: int,
    depth: int,
    config: GenerationConfig,
    rng: random.Random,
) -> typing.Any:
    node_kind = rng.choice(_enabled_node_kind_array(config=config, depth=depth))

    match node_kind:
        case "plain_scalar":
            return _generate_scalar(index=index, scalar_kind="plain")

        case "single_quoted_scalar":
            return _generate_scalar(index=index, scalar_kind="single_quoted")

        case "double_quoted_scalar":
            return _generate_scalar(index=index, scalar_kind="double_quoted")

        case "literal_block_scalar":
            return ruamel.yaml.scalarstring.LiteralScalarString(
                f"literal line one {index}\nliteral line two {index}\n"
            )

        case "folded_block_scalar":
            return ruamel.yaml.scalarstring.FoldedScalarString(
                f"folded line one {index}\nfolded line two {index}\n"
            )

        case "mapping":
            return _generate_mapping(
                index=index,
                depth=depth + 1,
                config=config,
                rng=rng,
                flow_style=False,
            )

        case "sequence":
            return _generate_sequence(
                index=index,
                depth=depth + 1,
                config=config,
                rng=rng,
                flow_style=False,
            )

        case "flow_mapping":
            return _generate_mapping(
                index=index,
                depth=depth + 1,
                config=config,
                rng=rng,
                flow_style=True,
            )

        case "flow_sequence":
            return _generate_sequence(
                index=index,
                depth=depth + 1,
                config=config,
                rng=rng,
                flow_style=True,
            )

        case _:
            raise ValueError(f"unknown node kind: {node_kind}")


def _generate_mapping(
    *,
    index: int,
    depth: int,
    config: GenerationConfig,
    rng: random.Random,
    flow_style: bool,
) -> ruamel.yaml.comments.CommentedMap:
    mapping = ruamel.yaml.comments.CommentedMap()

    for item_index in range(rng.randint(1, config.max_mapping_size)):
        child_index = index * 1000 + item_index

        mapping[f"key_{index}_{item_index}"] = _generate_node(
            index=child_index,
            depth=depth,
            config=config,
            rng=rng,
        )

    if flow_style:
        mapping.fa.set_flow_style()
    else:
        mapping.fa.set_block_style()

    return mapping


def _generate_sequence(
    *,
    index: int,
    depth: int,
    config: GenerationConfig,
    rng: random.Random,
    flow_style: bool,
) -> ruamel.yaml.comments.CommentedSeq:
    sequence = ruamel.yaml.comments.CommentedSeq()

    for item_index in range(rng.randint(1, config.max_sequence_size)):
        child_index = index * 1000 + item_index

        sequence.append(
            _generate_node(
                index=child_index,
                depth=depth,
                config=config,
                rng=rng,
            )
        )

    if flow_style:
        sequence.fa.set_flow_style()
    else:
        sequence.fa.set_block_style()

    return sequence


def _enabled_node_kind_array(
    *,
    config: GenerationConfig,
    depth: int,
) -> list[str]:
    node_kind_array: list[str] = []

    if config.plain_scalar:
        node_kind_array.append("plain_scalar")

    if config.single_quoted_scalar:
        node_kind_array.append("single_quoted_scalar")

    if config.double_quoted_scalar:
        node_kind_array.append("double_quoted_scalar")

    if config.literal_block_scalar:
        node_kind_array.append("literal_block_scalar")

    if config.folded_block_scalar:
        node_kind_array.append("folded_block_scalar")

    if depth < config.nested_level_count:
        if config.mapping:
            node_kind_array.append("mapping")

        if config.sequence:
            node_kind_array.append("sequence")

        if config.flow_mapping:
            node_kind_array.append("flow_mapping")

        if config.flow_sequence:
            node_kind_array.append("flow_sequence")

    if not node_kind_array:
        raise ValueError("at least one node kind must be enabled")

    return node_kind_array


def _choose_scalar_kind(
    *,
    config: GenerationConfig,
    rng: random.Random,
) -> str:
    scalar_kind_array: list[str] = []

    if config.plain_scalar:
        scalar_kind_array.append("plain")

    if config.single_quoted_scalar:
        scalar_kind_array.append("single_quoted")

    if config.double_quoted_scalar:
        scalar_kind_array.append("double_quoted")

    if not scalar_kind_array:
        raise ValueError("at least one scalar kind must be enabled")

    return rng.choice(scalar_kind_array)


def _generate_scalar(
    *,
    index: int,
    scalar_kind: str,
) -> typing.Any:
    match scalar_kind:
        case "plain":
            return f"value_{index}"

        case "single_quoted":
            return ruamel.yaml.scalarstring.SingleQuotedScalarString(f"single value {index}")

        case "double_quoted":
            return ruamel.yaml.scalarstring.DoubleQuotedScalarString(f"double value {index}")

        case _:
            raise ValueError(f"unknown scalar kind: {scalar_kind}")


def _dump_model(model: typing.Any) -> str:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.explicit_end = False

    stream = io.StringIO()
    yaml.dump(model, stream)

    body = stream.getvalue()
    line_array = body.splitlines()

    if line_array and line_array[-1] == "...":
        line_array.pop()
        body = "\n".join(line_array) + "\n"

    return body


def _decorate_body(
    body: str,
    *,
    config: GenerationConfig,
    rng: random.Random,
) -> str:
    output_line_array: list[str] = []
    block_scalar_header_indent: int | None = None

    for line in body.splitlines():
        current_indent = _indent_width(line)

        if block_scalar_header_indent is not None:
            if line.strip() == "":
                output_line_array.append(line)
                continue

            if current_indent > block_scalar_header_indent:
                output_line_array.append(line)
                continue

            block_scalar_header_indent = None

        if _is_block_scalar_header(line):
            block_scalar_header_indent = current_indent

        if config.blank_lines and rng.random() < 0.15:
            output_line_array.append("")

        if config.comments and rng.random() < 0.15:
            output_line_array.append(_generate_comment_line(current_indent, rng))

        if config.inline_comments and _can_have_inline_comment(line) and rng.random() < 0.20:
            line = f"{line}  # {_generate_comment_text(rng)}"

        output_line_array.append(line)

    return "\n".join(output_line_array) + "\n"


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_block_scalar_header(line: str) -> bool:
    stripped = line.rstrip()

    return stripped.endswith("|") or stripped.endswith(">")


def _can_have_inline_comment(line: str) -> bool:
    stripped = line.strip()

    if stripped == "":
        return False

    if stripped.startswith("#"):
        return False

    if stripped.endswith("|") or stripped.endswith(">"):
        return False

    return True


def _generate_comment_line(indent: int, rng: random.Random) -> str:
    return (" " * indent) + "# " + _generate_comment_text(rng)


def _generate_comment_text(rng: random.Random) -> str:
    return rng.choice(
        [
            "generated comment",
            "fuzz comment",
            "roundtrip comment",
            "lexer should preserve this",
        ]
    )
