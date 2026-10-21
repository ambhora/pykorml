# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import enum

import korml.model

__all__ = ["ErrorCode", "emit"]


class ErrorCode(str, enum.Enum):
    UNSUPPORTED_VALUE = "UNSUPPORTED_VALUE"

    def __str__(self) -> str:
        return self.value


def emit(
    stream: korml.model.Stream[object],
) -> str:
    if stream.version is not korml.model.Version.v1:
        raise ValueError(f"emitter v1 cannot emit version {stream.version.value!r}")

    output: list[str] = ["%!korml version 1.0"]

    if not stream.document_array:
        output.append("---")
        output.append("...")
        return "\n".join(output) + "\n"

    for document in stream.document_array:
        output.append("---")
        output.extend(_emit_value(document, indent=0))
        output.append("...")

    return "\n".join(output) + "\n"


def _emit_value(
    value: korml.model.Value[object],
    *,
    indent: int,
) -> list[str]:
    if isinstance(value, korml.model.Scalar):
        return _emit_scalar(value.value, indent=indent)

    if isinstance(value, korml.model.Sequence):
        return _emit_sequence(value, indent=indent)

    if isinstance(value, korml.model.Mapping):
        return _emit_mapping(value, indent=indent)

    raise TypeError(f"cannot emit {type(value).__name__!r}")


def _emit_scalar(
    value: str,
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if not _is_literal_block_safe(value):
        return [prefix + _format_double_quoted_scalar(value)]

    line_array = [prefix + "|"]
    line_array.extend(_literal_block_content_lines(value, indent=indent + 2))

    return line_array


def _emit_sequence(
    sequence: korml.model.Sequence[object],
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if not sequence.value_array:
        return [prefix + "[]"]

    line_array: list[str] = []

    for value in sequence.value_array:
        if isinstance(value, korml.model.Scalar):
            line_array.extend(_emit_sequence_scalar_item(value.value, indent=indent))
        else:
            line_array.append(prefix + "-")
            line_array.extend(_emit_value(value, indent=indent + 2))

    return line_array


def _emit_sequence_scalar_item(
    value: str,
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if not _is_literal_block_safe(value):
        return [prefix + "- " + _format_double_quoted_scalar(value)]

    line_array = [prefix + "- |"]
    line_array.extend(_literal_block_content_lines(value, indent=indent + 2))

    return line_array


def _emit_mapping(
    mapping: korml.model.Mapping[object],
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if not mapping.value_map:
        return [prefix + "{}"]

    line_array: list[str] = []

    for key, value in mapping.value_map.items():
        formatted_key = _format_double_quoted_scalar(key)

        if isinstance(value, korml.model.Scalar):
            line_array.extend(
                _emit_mapping_scalar_item(
                    formatted_key=formatted_key,
                    value=value.value,
                    indent=indent,
                )
            )
        else:
            line_array.append(prefix + formatted_key + ":")
            line_array.extend(_emit_value(value, indent=indent + 2))

    return line_array


def _emit_mapping_scalar_item(
    *,
    formatted_key: str,
    value: str,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if not _is_literal_block_safe(value):
        return [prefix + formatted_key + ": " + _format_double_quoted_scalar(value)]

    line_array = [prefix + formatted_key + ": |"]
    line_array.extend(_literal_block_content_lines(value, indent=indent + 2))

    return line_array


def _is_literal_block_safe(value: str) -> bool:
    """
    Return whether a literal block scalar reads back as exactly value.

    A literal block keeps one final line break and drops trailing blank
    lines, takes its indentation from its first line, and ends a line at any
    line break the lexer knows, including a bare carriage return. A value
    is written as a block only if none of that can change it: it ends with
    exactly one line feed, and every line is non-empty, starts and ends
    without whitespace and holds printable characters or tabs only. Every
    other value is written double-quoted, which always reads back exactly.
    """
    if not value.endswith("\n") or value.endswith("\n\n"):
        return False

    for line in value[:-1].split("\n"):
        if line == "" or line != line.strip(" \t"):
            return False
        if not all(char == "\t" or char.isprintable() for char in line):
            return False

    return True


def _literal_block_content_lines(
    value: str,
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent
    content = value[:-1]

    if content == "":
        return [prefix]

    return [prefix + line for line in content.split("\n")]


def _format_double_quoted_scalar(value: str) -> str:
    output = ['"']

    for char in value:
        match char:
            case "\\":
                output.append("\\\\")
            case '"':
                output.append('\\"')
            case "\0":
                output.append("\\0")
            case "\a":
                output.append("\\a")
            case "\b":
                output.append("\\b")
            case "\t":
                output.append("\\t")
            case "\n":
                output.append("\\n")
            case "\v":
                output.append("\\v")
            case "\f":
                output.append("\\f")
            case "\r":
                output.append("\\r")
            case _:
                output.append(char)

    output.append('"')

    return "".join(output)
