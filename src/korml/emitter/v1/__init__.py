# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""
KORML v1 emitter.

The emitter writes one canonical form: keys double-quoted, block collections
indented by two spaces per level, a scalar either double-quoted or, when that
reads back exactly, as a literal block scalar, and an empty collection as []
or {} on the line of its key or dash. Every output follows the Korml rules
and parses back to the same document.
"""

import enum

import korml._limits
import korml.error
import korml.model

__all__ = ["ErrorCode", "emit"]


class ErrorCode(str, enum.Enum):
    """The codes of the errors the emitter reports."""

    UNSUPPORTED_VALUE = "UNSUPPORTED_VALUE"
    """A value no source can hold, such as a string with a lone surrogate."""
    KEY_TOO_LONG = "KEY_TOO_LONG"
    """A key longer than MAX_KEY_LENGTH when written double-quoted."""
    TOO_DEEP = "TOO_DEEP"
    """Collections nested deeper than max_depth."""

    def __str__(self) -> str:
        return self.value


# The longest key a source may hold, in characters of source text.
MAX_KEY_LENGTH = 1024
"""The longest key a source may hold, in characters of source text."""

# The indentation width of every emitted document.
_INDENT_WIDTH = 2


def emit(
    stream: korml.model.Stream[object],
    *,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> str:
    """
    Return the v1 source of stream.

    An empty document (an Empty) is written as '---' then '...'. A stream
    without documents cannot be written as such, since a v1 stream holds at
    least one document; it is written as one empty document.

    max_depth is the deepest nesting of collections written; deeper nesting
    is an EmitError with the code TOO_DEEP. With None there is no korml
    limit, and nesting too deep for Python's recursion limit raises the
    same error.
    """
    if stream.version is not korml.model.Version.v1:
        raise ValueError(f"emitter v1 cannot emit version {stream.version.value!r}")

    korml._limits.check_max_depth(max_depth)
    output: list[str] = ["%!korml version 1.0"]

    for document in stream.document_array or [korml.model.Empty()]:
        output.append("---")
        output.extend(_emit_root(document, max_depth=max_depth))
        output.append("...")

    return "\n".join(output) + "\n"


def _too_deep_error(max_depth: int | None) -> korml.error.EmitError:
    return korml.error.EmitError(
        message=korml._limits.too_deep_message(max_depth),
        code=str(ErrorCode.TOO_DEEP),
    )


def _emit_root(value: korml.model.Value[object], *, max_depth: int | None) -> list[str]:
    """
    Return the lines of a document body whose root node is value.

    A block scalar cannot be the root node, so a root scalar is always
    double-quoted. An empty document has no lines. A RecursionError, only
    possible when max_depth is None or larger than Python can recurse,
    becomes an EmitError with the code TOO_DEEP.
    """
    if isinstance(value, korml.model.Empty):
        return []

    if isinstance(value, korml.model.Scalar):
        return [_format_double_quoted_scalar(value.value)]

    try:
        return _emit_collection(value, indent=0, depth=0, max_depth=max_depth)
    except RecursionError as error:
        raise _too_deep_error(max_depth) from error


def _emit_collection(
    value: korml.model.Value[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
) -> list[str]:
    if isinstance(value, korml.model.Empty):
        raise korml.error.EmitError(
            message="an empty document can only be the root of a document",
            code=str(ErrorCode.UNSUPPORTED_VALUE),
        )

    if korml._limits.is_too_deep(depth, max_depth):
        raise _too_deep_error(max_depth)

    if isinstance(value, korml.model.Sequence):
        if not value.value_array:
            return [" " * indent + "[]"]
        return _emit_sequence(value, indent=indent, depth=depth, max_depth=max_depth)

    if isinstance(value, korml.model.Mapping):
        if not value.value_map:
            return [" " * indent + "{}"]
        return _emit_mapping(value, indent=indent, depth=depth, max_depth=max_depth)

    raise TypeError(f"cannot emit {type(value).__name__!r}")


def _emit_entry(
    head: str,
    value: korml.model.Value[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
) -> list[str]:
    """
    Return the lines of a mapping or sequence entry whose key or dash is head.

    A scalar and an empty collection go on the line of head; a non-empty
    collection starts on the next line, one level deeper, since a block
    collection cannot start on the line of its key and a compact entry is
    not needed.
    """
    if isinstance(value, korml.model.Scalar):
        return _emit_scalar_entry(head, value.value, indent=indent)

    is_empty_collection = (isinstance(value, korml.model.Sequence) and not value.value_array) or (
        isinstance(value, korml.model.Mapping) and not value.value_map
    )

    line_array = _emit_collection(
        value,
        indent=0 if is_empty_collection else indent + _INDENT_WIDTH,
        depth=depth,
        max_depth=max_depth,
    )

    if is_empty_collection:
        return [head + " " + line_array[0]]

    return [head, *line_array]


def _emit_sequence(
    sequence: korml.model.Sequence[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
) -> list[str]:
    line_array: list[str] = []

    for value in sequence.value_array:
        line_array.extend(
            _emit_entry(
                " " * indent + "-", value, indent=indent, depth=depth + 1, max_depth=max_depth
            )
        )

    return line_array


def _emit_mapping(
    mapping: korml.model.Mapping[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
) -> list[str]:
    line_array: list[str] = []

    for key, value in mapping.value_map.items():
        formatted_key = _format_double_quoted_scalar(key)

        if len(formatted_key) > MAX_KEY_LENGTH:
            raise korml.error.EmitError(
                message=(
                    f"key is longer than {MAX_KEY_LENGTH} characters when written double-quoted"
                ),
                code=str(ErrorCode.KEY_TOO_LONG),
            )

        line_array.extend(
            _emit_entry(
                " " * indent + formatted_key + ":",
                value,
                indent=indent,
                depth=depth + 1,
                max_depth=max_depth,
            )
        )

    return line_array


def _emit_scalar_entry(head: str, value: str, *, indent: int) -> list[str]:
    """Return the lines of an entry whose value is a scalar, after head."""
    if not _is_literal_block_safe(value):
        return [head + " " + _format_double_quoted_scalar(value)]

    # The content indentation of a block scalar is the column of its key or
    # dash plus the indentation width.
    prefix = " " * (indent + _INDENT_WIDTH)

    return [head + " |", *(prefix + line for line in value[:-1].split("\n"))]


def _is_literal_block_safe(value: str) -> bool:
    """
    Return whether a literal block scalar reads back as exactly value.

    A literal block keeps one final line break and drops trailing empty
    lines, and its first content line fixes its indentation. A value is
    written as a block only if none of that can change it: it ends with
    exactly one line feed, and every line is non-empty, starts and ends
    without whitespace and holds printable characters or tabs only, so no
    character needs an escape. Every other value is written double-quoted,
    which always reads back exactly.
    """
    if not value.endswith("\n") or value.endswith("\n\n"):
        return False

    for line in value[:-1].split("\n"):
        if line == "" or line != line.strip(" \t"):
            return False
        if not all(char == "\t" or char.isprintable() for char in line):
            return False

    return True


# The escapes of double-quoted scalars that have a short form.
_SHORT_ESCAPE_MAP = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _escape_code_point(char: str) -> str:
    """Escape a character as \\uXXXX, or as \\UXXXXXXXX beyond the Basic Multilingual Plane."""
    code_point = ord(char)

    if code_point < 0x10000:
        return f"\\u{code_point:04x}"

    return f"\\U{code_point:08x}"


def _format_double_quoted_scalar(value: str) -> str:
    """
    Return value as a double-quoted scalar.

    Every character that is not printable is written as an escape. That
    covers every character a source may not hold raw (controls, separators,
    bidirectional controls, invisible characters and the zero-width joiners),
    so the result is valid in a value and in a key. A lone surrogate cannot
    be written at all: no escape denotes one, and UTF-8 cannot encode it.
    """
    output = ['"']

    for char in value:
        if char in _SHORT_ESCAPE_MAP:
            output.append(_SHORT_ESCAPE_MAP[char])
        elif 0xD800 <= ord(char) <= 0xDFFF:
            raise korml.error.EmitError(
                message=(
                    f"cannot emit a string that contains the lone surrogate U+{ord(char):04X}"
                ),
                code=str(ErrorCode.UNSUPPORTED_VALUE),
            )
        elif not char.isprintable():
            output.append(_escape_code_point(char))
        else:
            output.append(char)

    output.append('"')

    return "".join(output)
