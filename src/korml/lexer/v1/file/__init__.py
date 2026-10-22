# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""
Classic in-memory lexer implementation for korml.

This module implements the lexer entry point for source text that is already
available as one complete Python string. It does not own files, open streams,
perform buffering, or support incremental streaming input.

The caller is responsible for reading input from disk, standard input, memory, or
another source before calling lex(). The lexer only keeps a SourceFile object so
that diagnostics can refer back to the human-readable source name and original
text.

The lexer starts in VERSION_HEADER mode. In that mode it consumes comments and
blank lines until it finds the korml version directive. Once the version is
known, lexing can continue using the appropriate version-specific rules.

Public API:
    lex:
        Tokenize a complete korml source string.

    unlex:
        Convert token_array back to source text.

    File:
        Container for the tokenized representation of a korml source file.
"""

import dataclasses
import enum
import re
import sys

import korml._limits
import korml.core
import korml.lexer
import korml.lexer.v1
import korml.model

__all__ = ["lex", "unlex"]


_VERSION_DIRECTIVE_PATTERN = re.compile(r"%!korml\s+version\s+(?P<version>\d+\.\d+)(?=\s*(#|$))")


@dataclasses.dataclass(frozen=True, slots=True)
class SourceFile:
    """
    Source text together with its diagnostic name.

    SourceFile is intentionally small. It does not represent an open file handle
    and it does not perform any reading. It only stores the already-read source
    text and the name that should appear in diagnostics.

    Attributes:
        filename:
           Human-readable name of the source. Usually a file path, but it may
           also be a logical name such as "<stdin>" or "<memory>".

        value:
           Complete source text.
    """

    filename: str
    value: str


class LexerMode(enum.Enum):
    """
    Lexer operating mode.

    The lexer is stateful because different parts of the korml syntax require
    different tokenization rules. For example, the lexer initially searches for a
    version directive, later scans normal stream content, and temporarily enters
    scalar or flow modes when parsing nested constructs.
    """

    VERSION_HEADER = "VERSION_HEADER"
    STREAM = "STREAM"

    VALUE_START = "VALUE_START"
    FLOW_VALUE_START = "FLOW_VALUE_START"


@dataclasses.dataclass
class LexerState:
    """
    Mutable state carried through lexer functions.

    Lexer functions return an updated LexerState rather than modifying global
    state. The state records the current mode, current source position, current
    language version, and nesting/indentation information needed to interpret
    subsequent characters.

    Attributes:
        mode:
            Current lexer mode.

        position:
            Current position in the source text. The offset is the absolute
            character offset into SourceFile.value().

        flow_nesting_level:
            Nesting depth of flow-style constructs such as inline sequences or
            mappings.

        source_file:
            Source metadata and full source text being lexed.

        version:
            korml language version detected from the version directive. This is
            unknown while the lexer is still in VERSION_HEADER mode.
    """

    mode: LexerMode
    position: korml.core.Position
    flow_nesting_level: int
    source_file: SourceFile
    version: korml.model.Version = korml.model.Version.unknown
    debug: bool = False  # Set to True to enable debug output from the lexer.


def _advance_position(
    position: korml.core.Position,
    text: str,
) -> korml.core.Position:
    """
    Advance a source position over consumed text.

    This helper is the single place where the lexer updates line, column, and
    offset coordinates after consuming raw source text. Keeping this logic in
    one function helps ensure that all tokens use the same coordinate
    conventions.

    Args:
        position:
            Source position before consuming text.

        text:
            Text consumed from the source starting at position.

    Returns:
        The source position immediately after the consumed text.

    Notes:
        Columns are textual columns, not visual columns. Tabs and Unicode
        grapheme clusters may render with different visual widths, but they
        still advance the column by one codepoint here.
    """
    return korml.core.advance_position(position, text)


def _make_span(
    start: korml.core.Position,
    value: str,
) -> tuple[korml.core.Span, korml.core.Position]:
    """
    Build a source span for a consumed text fragment.

    Args:
        start:
            Source position at which value begins.

        value:
            Text fragment covered by the span.

    Returns:
        A tuple containing the span covering value and the position immediately
        after value.
    """
    end = _advance_position(start, value)
    return korml.core.Span(start=start, end=end), end


def _make_token(
    token_type: korml.lexer.v1.TokenType,
    value: str,
    start: korml.core.Position,
) -> tuple[korml.lexer.v1.Token, korml.core.Position]:
    """
    Build a lexer token and compute the following source position.

    Args:
        token_type:
            Type of token to create.

        value:
            Exact source text represented by the token.

        start:
            Source position at which the token begins.

    Returns:
        A tuple containing the created token and the source position immediately
        after the token.
    """
    span, end = _make_span(start, value)

    return (
        korml.lexer.v1.Token(
            type=token_type,
            value=value,
            span=span,
        ),
        end,
    )


def _read_until_newline(
    input_text: str,
    lexer_state: LexerState,
) -> str:
    """
    Read text from the current position up to the next newline.

    Args:
        input_text:
            Complete source text being lexed.

        lexer_state:
            Current lexer state. Reading begins at lexer_state.position.

    Returns:
        Source text from the current position up to, but not including, the next
        newline or the end of input.
    """
    start = lexer_state.position.offset
    end = start

    while end < len(input_text) and input_text[end] not in "\r\n":
        end += 1

    return input_text[start:end]


def _source_line(
    input_text: str,
    lexer_state: LexerState,
) -> str:
    """
    Return the whole source line that contains the current position.

    Diagnostics print it with a caret under the column of the position, so it
    starts at the beginning of the line, not at the position.
    """
    start = lexer_state.position.offset

    while start > 0 and input_text[start - 1] not in "\r\n":
        start -= 1

    end = lexer_state.position.offset

    while end < len(input_text) and input_text[end] not in "\r\n":
        end += 1

    return input_text[start:end]


def unlex(file: korml.lexer.v1.File) -> str:
    """
    Convert a tokenized korml file back to source text.

    Args:
        file:
            Tokenized korml file.

    Returns:
        Source text reconstructed by concatenating token values.
    """
    return "".join(token.value for token in file.token_array)


def _make_error_span(position: korml.core.Position) -> korml.core.Span:
    return korml.core.Span(start=position, end=position)


def _debug_lexer(lexer_state: LexerState, message: str) -> None:
    if not lexer_state.debug:
        return

    position = lexer_state.position
    source = lexer_state.source_file.value

    char = None
    if position.offset < len(source):
        char = source[position.offset]

    line_start = position.offset
    while line_start > 0 and source[line_start - 1] not in "\r\n":
        line_start -= 1

    line_end = position.offset
    while line_end < len(source) and source[line_end] not in "\r\n":
        line_end += 1

    line_text = source[line_start:line_end]

    pointer_column = position.offset - line_start
    pointer = " " * pointer_column + "^"

    print(
        "[lexer-debug] "
        f"{lexer_state.mode.value} "
        f"{position.line}:{position.column} "
        f"offset={position.offset} "
        f"char={char!r} "
        f"- {message}\n"
        f"    {line_text}\n"
        f"    {pointer}",
        file=sys.stderr,
    )


def _lex_flow_entry_separator(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex flow entry separator")

    position = lexer_state.position

    if input_text[position.offset] != ",":
        raise korml.error.BugError(
            message="_lex_flow_entry_separator() called without leading ','",
            location="korml.lexer._lex_flow_entry_separator",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.FLOW_SEPARATOR,
        ",",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=LexerMode.FLOW_VALUE_START,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_document_end(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex document end marker")

    position = lexer_state.position

    if not input_text.startswith("...", position.offset):
        raise korml.error.BugError(
            message="_lex_document_end() called without leading '...'",
            location="korml.lexer._lex_document_end",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.DOC_END,
        "...",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=LexerMode.STREAM,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def lex(
    filename: str,
    input_text: str,
    debug=False,
    *,
    max_tokens: int | None = None,
) -> korml.lexer.v1.File:
    lexer_state = LexerState(
        mode=LexerMode.VERSION_HEADER,
        position=korml.core.Position(1, 1, 0),
        flow_nesting_level=0,
        source_file=SourceFile(filename, input_text),
        version=korml.model.Version.unknown,
        debug=debug,
    )

    _debug_lexer(lexer_state, "start lexing")

    token_array: list[korml.lexer.v1.Token] = []

    while lexer_state.position.offset < len(input_text):
        korml._limits.check_token_count(len(token_array), max_tokens=max_tokens, filename=filename)
        char = input_text[lexer_state.position.offset]

        _debug_lexer(lexer_state, "dispatch")

        if char in "\r\n":
            _debug_lexer(lexer_state, "lex newline")
            token, lexer_state = _lex_newline(input_text, lexer_state)
            token_array.append(token)
            continue

        if char in " \t":
            token, lexer_state = _lex_horizontal_whitespace(input_text, lexer_state)
            token_array.append(token)
            continue

        if char == "#":
            token, lexer_state = _lex_comment(input_text, lexer_state)
            token_array.append(token)
            continue

        match lexer_state.mode:
            case LexerMode.VERSION_HEADER:
                token, lexer_state = _lex_version_directive(input_text, lexer_state)
                token_array.append(token)
                continue

            case LexerMode.STREAM:
                token, lexer_state = _lex_stream_token(input_text, lexer_state)
                token_array.append(token)
                continue

            case LexerMode.VALUE_START:
                token, lexer_state = _lex_value_start_token(input_text, lexer_state)
                token_array.append(token)
                continue

            case LexerMode.FLOW_VALUE_START:
                token, lexer_state = _lex_flow_value_start_token(input_text, lexer_state)
                token_array.append(token)
                continue

            case _:
                raise korml.error.BugError(
                    message="unsupported lexer mode in lex()",
                    location="korml.lexer.lex",
                    details=(
                        f"lex() reached a lexer mode that has no dispatch case: "
                        f"{lexer_state.mode!r}"
                    ),
                    source_name=lexer_state.source_file.filename,
                    span=_make_error_span(lexer_state.position),
                    source_line=_source_line(input_text, lexer_state),
                )

    if lexer_state.flow_nesting_level != 0:
        raise korml.error.LexError(
            message="unterminated flow collection",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    if lexer_state.version == korml.model.Version.unknown:
        raise korml.error.LexError(
            message="expected korml version directive",
            code=korml.lexer.v1.ErrorCode.MISSING_VERSION_DIRECTIVE,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    return korml.lexer.v1.File(
        token_array=token_array, version=lexer_state.version, filename=filename
    )


def _is_token_boundary(input_text: str, offset: int) -> bool:
    return offset >= len(input_text) or input_text[offset] in " \t\r\n#"


def _detect_block_scalar_indent(
    input_text: str,
    offset: int,
) -> int:
    while offset < len(input_text):
        line_start = offset
        line_end = offset

        while line_end < len(input_text) and input_text[line_end] not in "\r\n":
            line_end += 1

        line_text = input_text[line_start:line_end]

        if line_text.strip() != "":
            return len(line_text) - len(line_text.lstrip(" "))

        offset = line_end

        if offset < len(input_text) and input_text.startswith("\r\n", offset):
            offset += 2
        elif offset < len(input_text) and input_text[offset] in "\r\n":
            offset += 1

    return 0


def _block_scalar_parent_indent(input_text: str, indicator_offset: int) -> int:
    """
    Return the indentation of the node that owns the block scalar at offset.

    That is the column, counted from 0, of the mapping key or sequence dash
    the scalar is the value of, or -1 for a scalar at the start of a line.
    The content of the scalar must be indented deeper.
    """
    line_start = indicator_offset
    while line_start > 0 and input_text[line_start - 1] not in "\r\n":
        line_start -= 1

    prefix = input_text[line_start:indicator_offset]
    index = len(prefix) - len(prefix.lstrip(" "))
    parent_indent = -1

    while prefix.startswith("-", index) and prefix[index + 1 : index + 2] in (" ", "\t"):
        parent_indent = index
        index += 1
        while index < len(prefix) and prefix[index] in " \t":
            index += 1

    if prefix[index:].strip() != "":
        parent_indent = index

    return parent_indent


def _block_scalar_body_end(input_text: str, offset: int, *, parent_indent: int) -> int:
    """
    Return the offset after the content lines of a block scalar.

    The content indentation is that of the first non-blank line, which must
    be deeper than parent_indent; otherwise the scalar is empty and that line
    belongs to the enclosing node, as in YAML. Content continues over blank
    lines and lines indented at least as deep.
    """
    block_indent = _detect_block_scalar_indent(input_text, offset)
    if block_indent <= parent_indent:
        return offset

    while offset < len(input_text):
        line_start = offset
        line_end = offset

        while line_end < len(input_text) and input_text[line_end] not in "\r\n":
            line_end += 1

        line_text = input_text[line_start:line_end]

        if line_text.strip() != "":
            line_indent = len(line_text) - len(line_text.lstrip(" "))
            if line_indent < block_indent:
                break

        offset = line_end

        if offset < len(input_text) and input_text.startswith("\r\n", offset):
            offset += 2
        elif offset < len(input_text) and input_text[offset] in "\r\n":
            offset += 1

    return offset


def _lex_single_quoted_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex single-quoted scalar")

    position = lexer_state.position
    offset = position.offset

    if input_text[offset] != "'":
        raise korml.error.BugError(
            message="_lex_single_quoted_scalar() called without leading single quote",
            location="korml.lexer._lex_single_quoted_scalar",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    offset += 1

    while offset < len(input_text):
        char = input_text[offset]

        if char in "\r\n":
            raise korml.error.LexError(
                message="unterminated single-quoted scalar",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=_source_line(input_text, lexer_state),
            )

        # A doubled quote is an escaped quote inside the scalar.
        if input_text.startswith("''", offset):
            offset += 2
            continue

        if char == "'":
            offset += 1
            value = input_text[position.offset : offset]

            token, new_position = _make_token(
                korml.lexer.v1.TokenType.SQ_SCALAR,
                value,
                position,
            )

            new_state = dataclasses.replace(
                lexer_state,
                position=new_position,
                mode=_mode_after_value(lexer_state),
            )

            _debug_lexer_result(lexer_state, token, new_state)

            _validate_flow_value_boundary(input_text, new_state)

            return token, new_state

        offset += 1

    raise korml.error.LexError(
        message="unterminated single-quoted scalar",
        code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(position),
        source_line=_source_line(input_text, lexer_state),
    )


def _validate_flow_value_boundary(
    input_text: str,
    lexer_state: LexerState,
) -> None:
    if lexer_state.mode is not LexerMode.FLOW_VALUE_START:
        return

    offset = lexer_state.position.offset

    while offset < len(input_text) and input_text[offset] in " \t\r\n":
        offset += 1

    if offset >= len(input_text):
        return

    if input_text[offset] == "#":
        return

    if input_text[offset] not in ",]}:":
        raise korml.error.LexError(
            message="expected flow separator or flow collection end",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )


def _lex_double_quoted_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex double-quoted scalar")

    position = lexer_state.position
    offset = position.offset

    if input_text[offset] != '"':
        raise korml.error.BugError(
            message="_lex_double_quoted_scalar() called without leading double quote",
            location="korml.lexer._lex_double_quoted_scalar",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    offset += 1
    escaped = False

    while offset < len(input_text):
        char = input_text[offset]

        if char in "\r\n":
            raise korml.error.LexError(
                message="unterminated double-quoted scalar",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=_source_line(input_text, lexer_state),
            )

        if escaped:
            escaped = False
            offset += 1
            continue

        if char == "\\":
            escaped = True
            offset += 1
            continue

        if char == '"':
            offset += 1
            value = input_text[position.offset : offset]

            token, new_position = _make_token(
                korml.lexer.v1.TokenType.DQ_SCALAR,
                value,
                position,
            )

            new_state = dataclasses.replace(
                lexer_state,
                position=new_position,
                mode=_mode_after_value(lexer_state),
            )

            _debug_lexer_result(lexer_state, token, new_state)
            _validate_flow_value_boundary(input_text, new_state)

            return token, new_state

        offset += 1

    raise korml.error.LexError(
        message="unterminated double-quoted scalar",
        code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(position),
        source_line=_source_line(input_text, lexer_state),
    )


def _lex_flow_sequence_start(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a flow sequence start token.
    """
    _debug_lexer(lexer_state, "lex flow sequence start")

    position = lexer_state.position

    if input_text[position.offset] != "[":
        raise korml.error.BugError(
            message="_lex_flow_sequence_start() called without leading '['",
            location="korml.lexer._lex_flow_sequence_start",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
        "[",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        flow_nesting_level=lexer_state.flow_nesting_level + 1,
        mode=LexerMode.FLOW_VALUE_START,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_flow_mapping_start(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a flow mapping start token.
    """
    _debug_lexer(lexer_state, "lex flow mapping start")

    position = lexer_state.position

    if input_text[position.offset] != "{":
        raise korml.error.BugError(
            message="_lex_flow_mapping_start() called without leading '{'",
            location="korml.lexer._lex_flow_mapping_start",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.FLOW_MAPPING_START,
        "{",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        flow_nesting_level=lexer_state.flow_nesting_level + 1,
        mode=LexerMode.FLOW_VALUE_START,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_value_start_token(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume one token in VALUE_START mode.
    """
    _debug_lexer(lexer_state, "lex value start token")
    if lexer_state.mode is not LexerMode.VALUE_START:
        raise korml.error.BugError(
            message="_lex_value_start_token() called outside VALUE_START mode",
            location="korml.lexer._lex_value_start_token",
            details=f"current mode is {lexer_state.mode!r}",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    _debug_lexer(lexer_state, "peek value start char")

    position = lexer_state.position
    char = input_text[position.offset]

    match char:
        case "[":
            return _lex_flow_sequence_start(input_text, lexer_state)

        case "{":
            return _lex_flow_mapping_start(input_text, lexer_state)

        case '"':
            return _lex_double_quoted_scalar(input_text, lexer_state)

        case "'":
            return _lex_single_quoted_scalar(input_text, lexer_state)

        case "|":
            return _lex_literal_block_scalar(input_text, lexer_state)

        case ">":
            return _lex_folded_block_scalar(input_text, lexer_state)

        case ":" if _is_mapping_colon(input_text, position.offset, lexer_state):
            return _lex_colon(input_text, lexer_state)

        case "-":
            return _lex_dash_at_value_start(input_text, lexer_state)

        case "]":
            raise korml.error.LexError(
                message="unexpected flow sequence end",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=_source_line(input_text, lexer_state),
            )

        case "}":
            raise korml.error.LexError(
                message="unexpected flow mapping end",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=_source_line(input_text, lexer_state),
            )

        case ".":
            if input_text.startswith("...", position.offset):
                return _lex_document_end(input_text, lexer_state)

            return _lex_plain_scalar(input_text, lexer_state)

        case _:
            return _lex_plain_scalar(input_text, lexer_state)


def _lex_folded_block_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex folded block scalar")

    position = lexer_state.position

    if input_text[position.offset] != ">":
        raise korml.error.BugError(
            message="_lex_folded_block_scalar() called without leading '>'",
            location="korml.lexer._lex_folded_block_scalar",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    offset = position.offset + 1

    while offset < len(input_text) and input_text[offset] not in "\r\n":
        offset += 1

    if offset < len(input_text) and input_text.startswith("\r\n", offset):
        offset += 2
    elif offset < len(input_text) and input_text[offset] in "\r\n":
        offset += 1

    offset = _block_scalar_body_end(
        input_text,
        offset,
        parent_indent=_block_scalar_parent_indent(input_text, position.offset),
    )

    value = input_text[position.offset : offset]

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
        value,
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=LexerMode.VALUE_START,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_literal_block_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex literal block scalar")

    position = lexer_state.position

    if input_text[position.offset] != "|":
        raise korml.error.BugError(
            message="_lex_literal_block_scalar() called without leading '|'",
            location="korml.lexer._lex_literal_block_scalar",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    offset = position.offset + 1

    while offset < len(input_text) and input_text[offset] not in "\r\n":
        offset += 1

    if offset >= len(input_text):
        value = input_text[position.offset : offset]
    elif input_text.startswith("\r\n", offset):
        offset += 2
        value = input_text[position.offset : offset]
    else:
        offset += 1
        value = input_text[position.offset : offset]

    offset = _block_scalar_body_end(
        input_text,
        offset,
        parent_indent=_block_scalar_parent_indent(input_text, position.offset),
    )

    value = input_text[position.offset : offset]

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
        value,
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=LexerMode.VALUE_START,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_flow_value_start_token(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume one token in FLOW_VALUE_START mode.
    """
    _debug_lexer(lexer_state, "lex flow value start token")

    if lexer_state.mode is not LexerMode.FLOW_VALUE_START:
        raise korml.error.BugError(
            message="_lex_flow_value_start_token() called outside FLOW_VALUE_START mode",
            location="korml.lexer._lex_flow_value_start_token",
            details=f"current mode is {lexer_state.mode!r}",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    position = lexer_state.position
    char = input_text[position.offset]

    match char:
        case "]":
            return _lex_flow_sequence_end(input_text, lexer_state)

        case ",":
            return _lex_flow_entry_separator(input_text, lexer_state)

        case "[":
            return _lex_flow_sequence_start(input_text, lexer_state)

        case '"':
            return _lex_double_quoted_scalar(input_text, lexer_state)

        case "'":
            return _lex_single_quoted_scalar(input_text, lexer_state)

        case "{":
            return _lex_flow_mapping_start(input_text, lexer_state)

        case "}":
            return _lex_flow_mapping_end(input_text, lexer_state)

        case ":" if _is_mapping_colon(input_text, position.offset, lexer_state):
            return _lex_colon(input_text, lexer_state)

        case "|":
            raise korml.error.LexError(
                message="literal block scalar is not allowed inside flow collection",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=_source_line(input_text, lexer_state),
            )

        case ">":
            raise korml.error.LexError(
                message="folded block scalar is not allowed inside flow collection",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=_source_line(input_text, lexer_state),
            )
        case ".":
            if input_text.startswith("...", position.offset):
                raise korml.error.LexError(
                    message="document end marker is not allowed inside flow collection",
                    code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                    source_name=lexer_state.source_file.filename,
                    span=_make_error_span(position),
                    source_line=_source_line(input_text, lexer_state),
                )

            return _lex_plain_scalar(input_text, lexer_state)

        case _:
            return _lex_plain_scalar(input_text, lexer_state)


def _lex_flow_mapping_end(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex flow mapping end")

    position = lexer_state.position

    if input_text[position.offset] != "}":
        raise korml.error.BugError(
            message="_lex_flow_mapping_end() called without leading '}'",
            location="korml.lexer._lex_flow_mapping_end",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    new_flow_nesting_level = lexer_state.flow_nesting_level - 1

    if new_flow_nesting_level < 0:
        raise korml.error.LexError(
            message="unexpected flow mapping end",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.FLOW_MAPPING_END,
        "}",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        flow_nesting_level=new_flow_nesting_level,
        mode=(LexerMode.VALUE_START if new_flow_nesting_level == 0 else LexerMode.FLOW_VALUE_START),
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_flow_sequence_end(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex flow sequence end")

    position = lexer_state.position

    if input_text[position.offset] != "]":
        raise korml.error.BugError(
            message="_lex_flow_sequence_end() called without leading ']'",
            location="korml.lexer._lex_flow_sequence_end",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    new_flow_nesting_level = lexer_state.flow_nesting_level - 1

    if new_flow_nesting_level < 0:
        raise korml.error.LexError(
            message="unexpected flow sequence end",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
        "]",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        flow_nesting_level=new_flow_nesting_level,
        mode=(LexerMode.VALUE_START if new_flow_nesting_level == 0 else LexerMode.FLOW_VALUE_START),
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_colon(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex colon")

    position = lexer_state.position

    if input_text[position.offset] != ":":
        raise korml.error.BugError(
            message="_lex_colon() called without leading ':'",
            location="korml.lexer._lex_colon",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.COLON,
        ":",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=_mode_after_value(lexer_state),
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _is_mapping_colon(input_text: str, offset: int, lexer_state: LexerState) -> bool:
    """
    Return whether the ':' at offset separates a key from its value.

    As in YAML, a colon is a mapping indicator only when whitespace, a line
    break or the end of the input follows it, or, inside a flow collection, a
    flow indicator. After a quoted scalar or the end of a flow collection,
    which cannot continue a plain scalar, any colon is an indicator, so
    JSON-style {"a":1} keeps working. Any other colon belongs to a plain
    scalar, as in http://example.org:8080 or 12:30.
    """
    following = offset + 1
    if following >= len(input_text) or input_text[following] in " \t\r\n":
        return True
    if lexer_state.flow_nesting_level > 0 and input_text[following] in ",[]{}":
        return True
    return offset > 0 and input_text[offset - 1] in "\"']}"


def _mode_after_value(lexer_state: LexerState) -> LexerMode:
    if lexer_state.flow_nesting_level > 0:
        return LexerMode.FLOW_VALUE_START

    return LexerMode.VALUE_START


_EXCLUDED_INDICATOR_MESSAGE_MAP = {
    "&": "anchors are not supported in korml",
    "*": "aliases are not supported in korml",
    "!": "tags are not supported in korml",
    "%": "directives are not supported in korml",
    "@": "'@' is reserved and cannot start a plain scalar",
    "`": "'`' is reserved and cannot start a plain scalar",
}


def _reject_excluded_indicator(input_text: str, lexer_state: LexerState) -> None:
    """
    Raise a LexError if a plain scalar would start with a YAML indicator.

    YAML gives these characters a meaning at the start of a node: anchors,
    aliases, tags, directives, complex keys, and two reserved characters.
    Korml excludes those features, and reading them as text would make korml
    and YAML disagree about the same source, so they are errors instead.
    """
    offset = lexer_state.position.offset
    char = input_text[offset]
    message = _EXCLUDED_INDICATOR_MESSAGE_MAP.get(char)

    if char == "?" and _is_token_boundary(input_text, offset + 1):
        message = "complex mapping keys are not supported in korml"

    if message is None:
        return

    raise korml.error.LexError(
        message=message,
        code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(lexer_state.position),
        source_line=_source_line(input_text, lexer_state),
    )


def _lex_plain_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex plain scalar")
    position = lexer_state.position
    offset = position.offset

    while offset < len(input_text):
        char = input_text[offset]

        if char in "\r\n":
            break

        # A comment needs whitespace before it; value#x is one scalar.
        if char == "#" and input_text[offset - 1] in " \t":
            break

        # Flow indicators end a plain scalar only inside a flow collection; in
        # block context, a: hello, world and a: x[1] are plain scalars.
        if char in "[]{}," and lexer_state.flow_nesting_level > 0:
            break

        if char == ":" and _is_mapping_colon(input_text, offset, lexer_state):
            break

        offset += 1

    value = input_text[position.offset : offset].rstrip()

    _reject_excluded_indicator(input_text, lexer_state)

    # As in YAML, a flow indicator cannot start a plain scalar.
    if value == "" or value[0] in ",[]{}":
        raise korml.error.LexError(
            message="expected plain scalar",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.PLAIN_SCALAR,
        value,
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=_mode_after_value(lexer_state),
    )

    _debug_lexer_result(lexer_state, token, new_state)
    _validate_flow_value_boundary(input_text, new_state)
    return token, new_state


def _lex_stream_token(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume one token in STREAM mode.

    STREAM mode expects the start of a document. For v1, this begins with the
    document-start marker "---". After this token, the lexer moves to
    VALUE_START mode.
    """
    if lexer_state.mode is not LexerMode.STREAM:
        raise korml.error.BugError(
            message="_lex_stream_token() called outside STREAM mode",
            location="korml.lexer._lex_stream_token",
            details=f"current mode is {lexer_state.mode!r}",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    position = lexer_state.position

    if not input_text.startswith("---", position.offset):
        raise korml.error.LexError(
            message="expected document start marker",
            code=korml.lexer.v1.ErrorCode.MISSING_DOCUMENT_START,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.DOC_START,
        "---",
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        mode=LexerMode.VALUE_START,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_dash_at_value_start(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex dash at value start")

    position = lexer_state.position

    if input_text.startswith("---", position.offset) and _is_token_boundary(
        input_text,
        position.offset + 3,
    ):
        raise korml.error.LexError(
            message="unexpected document start marker",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    next_offset = position.offset + 1

    if next_offset >= len(input_text) or input_text[next_offset] in " \t\r\n":
        token, new_position = _make_token(
            korml.lexer.v1.TokenType.DASH_ITEM,
            "-",
            position,
        )

        new_state = dataclasses.replace(
            lexer_state,
            position=new_position,
            mode=LexerMode.VALUE_START,
        )

        _debug_lexer_result(lexer_state, token, new_state)

        return token, new_state

    return _lex_plain_scalar(input_text, lexer_state)


def _lex_version_directive(
    input_text: str, lexer_state: LexerState
) -> tuple[korml.lexer.v1.Token, LexerState]:
    _debug_lexer(lexer_state, "lex version directive")
    position = lexer_state.position
    line_text = _read_until_newline(input_text, lexer_state)

    match = _VERSION_DIRECTIVE_PATTERN.match(line_text)

    if match is None:
        raise korml.error.LexError(
            message="expected korml version directive",
            code=korml.lexer.v1.ErrorCode.MISSING_VERSION_DIRECTIVE,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    value = match.group(0)
    version_text = match.group("version")

    match version_text:
        case "1.0":
            version = korml.model.Version.v1
        case _:
            raise korml.error.LexError(
                message="expected korml version directive",
                code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(lexer_state.position),
                source_line=_source_line(input_text, lexer_state),
            )

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.VERSION_DIRECTIVE,
        value,
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
        version=version,
        mode=LexerMode.STREAM,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _lex_newline(
    input_text: str, lexer_state: LexerState
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a newline sequence.

    This function recognizes both Unix ("\n") and Windows ("\r\n")
    newline encodings and produces a single NEWLINE token.

    Args:
        input_text:
            Complete source text being lexed.

        lexer_state:
            Current lexer state. The current position must point to the
            beginning of a newline sequence.

    Returns:
        A tuple containing the produced NEWLINE token and the updated lexer
        state after consuming the newline.
    """
    _debug_lexer(lexer_state, "lex newline")
    position = lexer_state.position
    offset = position.offset

    if input_text.startswith("\r\n", offset):
        value = "\r\n"
    else:
        value = input_text[offset]

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.NEWLINE,
        value,
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _reject_tab_indentation(
    input_text: str,
    lexer_state: LexerState,
    *,
    value: str,
    end: int,
) -> None:
    """
    Raise a LexError if a tab indents content in block context.

    Indentation decides the structure of a block collection, and a tab has
    no defined width, so, as in YAML, block indentation is spaces only. A tab
    before a comment, at the end of a line, inside a line or inside a flow
    collection is ordinary whitespace.
    """
    at_line_start = lexer_state.position.column == 1
    ends_line = end >= len(input_text) or input_text[end] in "\r\n#"

    if "\t" not in value or not at_line_start or ends_line:
        return

    if lexer_state.flow_nesting_level > 0:
        return

    raise korml.error.LexError(
        message="tabs are not allowed in indentation; indent with spaces",
        code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(lexer_state.position),
        source_line=_source_line(input_text, lexer_state),
    )


def _lex_horizontal_whitespace(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a run of horizontal whitespace.

    Horizontal whitespace consists of spaces and tab characters. Newlines
    are handled separately by _lex_newline().

    Args:
        input_text:
            Complete source text being lexed.

        lexer_state:
            Current lexer state. The current position must point to a space
            or tab character.

    Returns:
        A tuple containing the produced WHITESPACE token and the updated
        lexer state after consuming the whitespace.
    """
    position = lexer_state.position
    offset = position.offset

    while offset < len(input_text) and input_text[offset] in " \t":
        offset += 1

    value = input_text[position.offset : offset]

    _reject_tab_indentation(input_text, lexer_state, value=value, end=offset)

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.WHITESPACE,
        value,
        position,
    )

    return token, dataclasses.replace(
        lexer_state,
        position=new_position,
    )


def _lex_comment(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a comment until the end of the current line.

    The returned COMMENT token includes the leading '#' character but does
    not include the terminating newline. The newline remains to be consumed
    separately by _lex_newline().

    Args:
        input_text:
            Complete source text being lexed.

        lexer_state:
            Current lexer state. The current position must point to the '#'
            character that begins the comment.

    Returns:
        A tuple containing the produced COMMENT token and the updated lexer
        state after consuming the comment text.
    """
    position = lexer_state.position
    value = _read_until_newline(input_text, lexer_state)

    token, new_position = _make_token(
        korml.lexer.v1.TokenType.COMMENT,
        value,
        position,
    )

    new_state = dataclasses.replace(
        lexer_state,
        position=new_position,
    )

    _debug_lexer_result(lexer_state, token, new_state)

    return token, new_state


def _raise_lexer_bug(
    *,
    message: str,
    lexer_state: LexerState,
    location: str,
    details: str | None = None,
) -> None:
    raise korml.error.BugError(
        message=message,
        location=location,
        details=details,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(lexer_state.position),
        source_line=_source_line(
            lexer_state.source_file.value,
            lexer_state,
        ),
    )


def _debug_lexer_result(
    old_state: LexerState,
    token: korml.lexer.v1.Token,
    new_state: LexerState,
) -> None:
    if not old_state.debug:
        return

    print(
        "[lexer-result] "
        f"token={token.type.name} "
        f"value={token.value!r} "
        f"mode={old_state.mode.value}->{new_state.mode.value}\n",
        file=sys.stderr,
    )
