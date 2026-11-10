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
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    """Output longer than max_output_bytes."""

    def __str__(self) -> str:
        """
        Return the code as text.

        @return The value of the code.
        """
        return self.value


# The longest key a source may hold, in characters of source text.
MAX_KEY_LENGTH = 1024
"""The longest key a source may hold, in characters of source text."""

# The indentation width of every emitted document.
_INDENT_WIDTH = 2


class _OutputBudget:
    """
    The bytes of output an emitter may still write.

    Every line is charged once, where it is produced, with its UTF-8 length
    and its line break, so the emitter refuses an output larger than the
    limit before it has built it. Indentation grows with nesting and is
    repeated on every line, so the output of a deeply nested document can be
    many times the size of the source it was read from.
    """

    __slots__ = ("limit", "used")

    def __init__(self, limit: int | None) -> None:
        """
        Initialize a budget with nothing used.

        @param limit The largest output allowed, in bytes, or None for no limit.
        """
        self.limit = limit
        """The largest output allowed, in bytes, or None for no limit."""
        self.used = 0
        """The bytes charged so far."""

    def charge(self, size: int) -> None:
        """
        Charge size bytes, and raise an EmitError if the output exceeds the limit.

        @param size The number of bytes to charge.
        """
        self.used += size

        if self.limit is not None and self.used > self.limit:
            raise korml.error.EmitError(
                message=f"output exceeds {self.limit} bytes",
                code=str(ErrorCode.OUTPUT_TOO_LARGE),
            )

    def line(self, text: str) -> str:
        """
        Charge a line and its line break, and return it.

        @param text The line, without its line break.

        @return text.
        """
        self.charge(_utf8_length(text) + 1)
        return text


def _utf8_length(text: str) -> int:
    """
    Return the length of text in UTF-8.

    @param text The text.

    @return The number of bytes.
    """
    if text.isascii():
        return len(text)

    return len(text.encode("utf-8", errors="surrogatepass"))


def emit(
    stream: korml.model.Stream[object],
    *,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
    max_output_bytes: int | None = korml._limits.MAX_OUTPUT_BYTES,
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

    max_output_bytes is the longest source written, in bytes of UTF-8; a
    longer one is an EmitError with the code OUTPUT_TOO_LARGE, raised before
    the source is built. The default, 4 GiB, only stops a memory bomb; with
    None there is no limit.

    @param stream The stream to write, of version v1.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param max_output_bytes The longest source allowed, in bytes, or None for no limit.

    @return The source, with its directive and document markers.
    """
    if stream.version is not korml.model.Version.v1:
        raise ValueError(f"emitter v1 cannot emit version {stream.version.value!r}")

    korml._limits.check_max_depth(max_depth)
    korml._limits.check_max_output_bytes(max_output_bytes)
    budget = _OutputBudget(max_output_bytes)
    output: list[str] = [budget.line("%!korml version 1.0")]

    for document in stream.document_array or [korml.model.Empty()]:
        output.append(budget.line("---"))
        output.extend(_emit_root(document, max_depth=max_depth, budget=budget))
        output.append(budget.line("..."))

    return "\n".join(output) + "\n"


def _too_deep_error(max_depth: int | None) -> korml.error.EmitError:
    """
    Return the error for nesting deeper than max_depth.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The error, with the code TOO_DEEP.
    """
    return korml.error.EmitError(
        message=korml._limits.too_deep_message(max_depth),
        code=str(ErrorCode.TOO_DEEP),
    )


def _emit_root(
    value: korml.model.Value[object], *, max_depth: int | None, budget: _OutputBudget
) -> list[str]:
    """
    Return the lines of a document body whose root node is value.

    A block scalar cannot be the root node, so a root scalar is always
    double-quoted. An empty document has no lines. A RecursionError, only
    possible when max_depth is None or larger than Python can recurse,
    becomes an EmitError with the code TOO_DEEP.

    @param value The root value of the document.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param budget The output still allowed, charged with every line.

    @return The lines, without line breaks.
    """
    if isinstance(value, korml.model.Empty):
        return []

    if isinstance(value, korml.model.Scalar):
        return [budget.line(_format_double_quoted_scalar(value.value))]

    try:
        line_array = _emit_collection(value, indent=0, depth=0, max_depth=max_depth, budget=budget)
    except RecursionError as error:
        raise _too_deep_error(max_depth) from error

    if _is_empty_collection(value):
        budget.line(line_array[0])

    return line_array


def _emit_collection(
    value: korml.model.Value[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
    budget: _OutputBudget,
) -> list[str]:
    """
    Return the lines of a sequence or mapping at a column.

    The line of an empty collection is not charged to budget, since the
    caller may join it to the line of a key or dash.

    @param value The collection to write.

    @param indent The column the entries of this collection start at.

    @param depth The number of collections around this one.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param budget The output still allowed, charged with every line of an entry.

    @return The lines, without line breaks.
    """
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
        return _emit_sequence(value, indent=indent, depth=depth, max_depth=max_depth, budget=budget)

    if isinstance(value, korml.model.Mapping):
        if not value.value_map:
            return [" " * indent + "{}"]
        return _emit_mapping(value, indent=indent, depth=depth, max_depth=max_depth, budget=budget)

    raise TypeError(f"cannot emit {type(value).__name__!r}")


def _emit_entry(
    head: str,
    value: korml.model.Value[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
    budget: _OutputBudget,
) -> list[str]:
    """
    Return the lines of a mapping or sequence entry whose key or dash is head.

    A scalar and an empty collection go on the line of head; a non-empty
    collection starts on the next line, one level deeper, since a block
    collection cannot start on the line of its key and a compact entry is
    not needed.

    @param head The text of the line so far: the indentation and the key or dash.

    @param value The value of the entry.

    @param indent The column of the key or dash.

    @param depth The number of collections around the value.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param budget The output still allowed, charged with every line.

    @return The lines, without line breaks.
    """
    if isinstance(value, korml.model.Scalar):
        return _emit_scalar_entry(head, value.value, indent=indent, budget=budget)

    is_empty_collection = _is_empty_collection(value)

    if not is_empty_collection:
        budget.line(head)

    line_array = _emit_collection(
        value,
        indent=0 if is_empty_collection else indent + _INDENT_WIDTH,
        depth=depth,
        max_depth=max_depth,
        budget=budget,
    )

    if is_empty_collection:
        return [budget.line(head + " " + line_array[0])]

    return [head, *line_array]


def _is_empty_collection(value: korml.model.Value[object]) -> bool:
    """
    Return whether value is a sequence or mapping without entries.

    @param value The value.

    @return True for an empty sequence or mapping.
    """
    return (isinstance(value, korml.model.Sequence) and not value.value_array) or (
        isinstance(value, korml.model.Mapping) and not value.value_map
    )


def _emit_sequence(
    sequence: korml.model.Sequence[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
    budget: _OutputBudget,
) -> list[str]:
    """
    Return the lines of a non-empty sequence, one entry after another.

    @param sequence The sequence to write.

    @param indent The column the entries of this collection start at.

    @param depth The number of collections around this one.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param budget The output still allowed, charged with every line.

    @return The lines, without line breaks.
    """
    line_array: list[str] = []

    for value in sequence.value_array:
        line_array.extend(
            _emit_entry(
                " " * indent + "-",
                value,
                indent=indent,
                depth=depth + 1,
                max_depth=max_depth,
                budget=budget,
            )
        )

    return line_array


def _emit_mapping(
    mapping: korml.model.Mapping[object],
    *,
    indent: int,
    depth: int,
    max_depth: int | None,
    budget: _OutputBudget,
) -> list[str]:
    """
    Return the lines of a non-empty mapping, one entry after another.

    @param mapping The mapping to write.

    @param indent The column the entries of this collection start at.

    @param depth The number of collections around this one.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param budget The output still allowed, charged with every line.

    @return The lines, without line breaks.
    """
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
                budget=budget,
            )
        )

    return line_array


def _emit_scalar_entry(head: str, value: str, *, indent: int, budget: _OutputBudget) -> list[str]:
    """
    Return the lines of an entry whose value is a scalar, after head.

    A block scalar is charged to budget before any of its lines is built,
    since its indentation is repeated on every line of the value.

    @param head The text of the line so far: the indentation and the key or dash.

    @param value The string of the scalar.

    @param indent The column of the key or dash.

    @param budget The output still allowed, charged with every line.

    @return The lines, without line breaks.
    """
    if not _is_literal_block_safe(value):
        # Built before it is charged; its size is bounded by value itself.
        return [budget.line(head + " " + _format_double_quoted_scalar(value))]

    # The content indentation of a block scalar is the column of its key or
    # dash plus the indentation width.
    prefix = " " * (indent + _INDENT_WIDTH)

    # The head line with ' |', then each line of value after prefix; value
    # ends with its only final line feed, which is the break of its last line.
    budget.charge(
        _utf8_length(head) + len(" |\n") + value.count("\n") * len(prefix) + _utf8_length(value)
    )

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

    @param value The string to write.

    @return True if a literal block scalar can hold it exactly.
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
    """
    Escape a character as \\uXXXX, or as \\UXXXXXXXX beyond the Basic Multilingual Plane.

    @param char The character to escape.

    @return The escape, in lower-case hexadecimal.
    """
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

    @param value The string to write.

    @return The scalar, quotes included.
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
