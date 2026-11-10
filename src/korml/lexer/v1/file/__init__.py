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
import unicodedata

import korml._limits
import korml.core
import korml.lexer
import korml.lexer.v1
import korml.model

__all__ = ["check_source_text", "lex", "unlex"]


# The directive is one fixed line: single spaces, no comment, only trailing
# whitespace after the version, so every reader finds the version the same way.
_VERSION_DIRECTIVE_PATTERN = re.compile(r"%!korml version (?P<version>[^ \t]+)[ \t]*")

# The characters that must not appear raw anywhere in a source: controls other
# than TAB, LF and CR, surrogates, the noncharacters U+FFFE and U+FFFF, the
# Unicode line and paragraph separators, the byte-order mark, bidirectional
# controls and invisible separators. Each of them either breaks line counting
# in some tool or makes text look different from what it is (a key "admin"
# followed by a zero-width space displays as "admin"). They can still be
# written as escapes in a double-quoted scalar.
_FORBIDDEN_CHARACTER_PATTERN = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff￾￿  ﻿؜‎‏‪-‮⁦-⁩​⁠]"
)

# Zero-width joiners are legitimate text in some scripts, so quoted values,
# block scalars and comments may hold them raw; in a plain scalar or a key
# they would make two different strings look the same.
JOINER_CHARACTER_SET = frozenset("‌‍")
"""The zero-width joiners, allowed raw except in plain scalars and keys."""


def _describe_character(char: str) -> str:
    """
    Return the code point and the name of a character, for a message.

    @param char The character.

    @return Text such as 'U+200B ZERO WIDTH SPACE'.
    """
    code_point = ord(char)
    name = unicodedata.name(char, "")

    if 0xD800 <= code_point <= 0xDFFF:
        name = "SURROGATE"
    elif char == "﻿":
        name = "BYTE ORDER MARK"
    elif name == "":
        name = unicodedata.category(char) == "Cc" and "CONTROL CHARACTER" or "NONCHARACTER"

    return f"U+{code_point:04X} {name}"


def _position_at_offset(input_text: str, offset: int) -> korml.core.Position:
    """
    Return the source position of an offset.

    @param input_text The complete source text.

    @param offset The offset into input_text, in code points.

    @return The position.
    """
    return korml.core.advance_position(korml.core.Position(1, 1, 0), input_text[:offset])


def _line_at_offset(input_text: str, offset: int) -> str:
    """
    Return the whole line that holds an offset.

    @param input_text The complete source text.

    @param offset The offset into input_text, in code points.

    @return The line, without its line break.
    """
    start = offset
    while start > 0 and input_text[start - 1] not in "\r\n":
        start -= 1

    end = offset
    while end < len(input_text) and input_text[end] not in "\r\n":
        end += 1

    return input_text[start:end]


def _raise_source_text_error(
    filename: str,
    input_text: str,
    offset: int,
    *,
    message: str,
    code: korml.lexer.v1.ErrorCode,
) -> None:
    """
    Raise a LexError located at an offset of the source.

    @param filename The name of the source, for diagnostics.

    @param input_text The complete source text.

    @param offset The offset of the problem.

    @param message What is wrong.

    @param code The error code.
    """
    position = _position_at_offset(input_text, offset)
    raise korml.error.LexError(
        message=message,
        code=code,
        source_name=filename,
        span=korml.core.Span(start=position, end=position),
        source_line=_line_at_offset(input_text, offset),
    )


def check_source_text(filename: str, input_text: str) -> None:
    """
    Raise a LexError if the source text breaks a character or line-break rule.

    These rules hold for the whole source, comments included, so they are
    checked once before tokenizing rather than in every token rule: no
    forbidden character (see _FORBIDDEN_CHARACTER_PATTERN), no byte-order
    mark anywhere, and line breaks that are either all LF or all CRLF, with
    no lone CR. A source mixing line-break styles counts lines differently
    in different tools, so diagnostics and reviews would point at different
    lines.

    @param filename The name of the source, for diagnostics.

    @param input_text The complete source text.
    """
    match = _FORBIDDEN_CHARACTER_PATTERN.search(input_text)

    if match is not None:
        char = match.group(0)
        hint = (
            "it cannot be encoded as UTF-8"
            if 0xD800 <= ord(char) <= 0xDFFF
            else "write it as an escape in a double-quoted scalar"
        )
        _raise_source_text_error(
            filename,
            input_text,
            match.start(),
            message=f"character {_describe_character(char)} is not allowed in korml source; {hint}",
            code=korml.lexer.v1.ErrorCode.INVALID_CHARACTER,
        )

    lone_carriage_return = re.search(r"\r(?!\n)", input_text)

    if lone_carriage_return is not None:
        _raise_source_text_error(
            filename,
            input_text,
            lone_carriage_return.start(),
            message="a carriage return must be followed by a line feed",
            code=korml.lexer.v1.ErrorCode.INVALID_LINE_BREAK,
        )

    first_line_feed = input_text.find("\n")

    if first_line_feed < 0:
        return

    if first_line_feed > 0 and input_text[first_line_feed - 1] == "\r":
        other_style = re.search(r"(?<!\r)\n", input_text)
        message = "line break LF in a source that uses CRLF; use one style throughout"
    else:
        other_style = re.search(r"\r\n", input_text)
        message = "line break CRLF in a source that uses LF; use one style throughout"

    if other_style is not None:
        _raise_source_text_error(
            filename,
            input_text,
            other_style.start(),
            message=message,
            code=korml.lexer.v1.ErrorCode.INVALID_LINE_BREAK,
        )


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
    """The name of the source, for diagnostics."""
    value: str
    """The complete source text."""


class LexerMode(enum.Enum):
    """
    Lexer operating mode.

    The lexer is stateful because different parts of the korml syntax require
    different tokenization rules. For example, the lexer initially searches for a
    version directive, later scans normal stream content, and temporarily enters
    scalar or flow modes when parsing nested constructs.
    """

    VERSION_HEADER = "VERSION_HEADER"
    """Looking for the version directive."""
    STREAM = "STREAM"
    """Between documents, looking for a document start marker."""

    VALUE_START = "VALUE_START"
    """Inside a document, outside any flow collection."""
    FLOW_VALUE_START = "FLOW_VALUE_START"
    """Inside a flow collection."""


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
    """What the lexer expects next."""
    position: korml.core.Position
    """Where the lexer is in the source."""
    flow_nesting_level: int
    """The number of flow collections open here."""
    source_file: SourceFile
    """The source being lexed."""
    version: korml.model.Version = korml.model.Version.unknown
    """The language version; unknown until the directive is read."""
    debug: bool = False  # Set to True to enable debug output from the lexer.
    """Whether to trace the lexer on standard error."""


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

    Notes:
        Columns are textual columns, not visual columns. Tabs and Unicode
        grapheme clusters may render with different visual widths, but they
        still advance the column by one codepoint here.

    @param position Source position before consuming text.

    @param text Text consumed from the source starting at position.

    @return The source position immediately after the consumed text.
    """
    return korml.core.advance_position(position, text)


def _make_span(
    start: korml.core.Position,
    value: str,
) -> tuple[korml.core.Span, korml.core.Position]:
    """
    Build a source span for a consumed text fragment.

    @param start Source position at which value begins.

    @param value Text fragment covered by the span.

    @return A tuple containing the span covering value and the position immediately after value.
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

    @param token_type Type of token to create.

    @param value Exact source text represented by the token.

    @param start Source position at which the token begins.

    @return A tuple containing the created token and the source position immediately after the
        token.
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

    @param input_text Complete source text being lexed.

    @param lexer_state Current lexer state. Reading begins at lexer_state.position.

    @return Source text from the current position up to, but not including, the next newline or the
        end of input.
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

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The line, without its line break.
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

    @param file Tokenized korml file.

    @return Source text reconstructed by concatenating token values.
    """
    return "".join(token.value for token in file.token_array)


def _make_error_span(position: korml.core.Position) -> korml.core.Span:
    """
    Return the empty span at position.

    @param position The position of the error.

    @return The span.
    """
    return korml.core.Span(start=position, end=position)


def _debug_lexer(lexer_state: LexerState, message: str) -> None:
    """
    Print the lexer state on standard error, if tracing is on.

    @param lexer_state The lexer state at the current position.

    @param message What the lexer is doing.
    """
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
    """
    Consume the ',' between two entries of a flow collection.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
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
    """
    Consume a document end marker, refusing one inside a flow collection.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
    _debug_lexer(lexer_state, "lex document end marker")

    position = lexer_state.position

    if lexer_state.flow_nesting_level != 0:
        raise korml.error.LexError(
            message="unterminated flow collection before document end marker",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

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
    """
    Tokenize a complete v1 source, refusing more than max_tokens tokens.

    @param filename The name of the source, for diagnostics.

    @param input_text The complete source text.

    @param debug Whether to trace the lexer on standard error.

    @param max_tokens The largest number of tokens accepted, or None for no limit.

    @return The tokens of the source.
    """
    check_source_text(str(filename), input_text)

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

    # Every document, the last one included, ends with '...', so a truncated
    # stream is an error rather than a shorter document.
    if lexer_state.mode is not LexerMode.STREAM:
        raise korml.error.LexError(
            message="document is not terminated by '...'",
            code=korml.lexer.v1.ErrorCode.MISSING_DOCUMENT_END,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    if not any(token.type is korml.lexer.v1.TokenType.DOC_START for token in token_array):
        raise korml.error.LexError(
            message="expected document start marker",
            code=korml.lexer.v1.ErrorCode.MISSING_DOCUMENT_START,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    return korml.lexer.v1.File(
        token_array=token_array, version=lexer_state.version, filename=filename
    )


def _is_marker_line(input_text: str, lexer_state: LexerState, marker: str) -> bool:
    """
    Return whether the current position starts a '---' or '...' marker line.

    A marker starts at column 0 and is alone on its line, apart from
    trailing whitespace: no content and no comment follow it.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @param marker The marker, '---' or '...'.

    @return True if the marker starts here and is alone on its line.
    """
    offset = lexer_state.position.offset

    if lexer_state.position.column != 1 or not input_text.startswith(marker, offset):
        return False

    rest = _read_until_newline(
        input_text,
        dataclasses.replace(lexer_state, position=_advance_position(lexer_state.position, marker)),
    )

    return rest.strip(" \t") == ""


def _block_scalar_parent_indent(input_text: str, indicator_offset: int) -> int:
    """
    Return the indentation of the node that owns the block scalar at offset.

    That is the column, counted from 0, of the mapping key or sequence dash
    the scalar is the value of, or -1 for a scalar at the start of a line.
    The content of the scalar must be indented deeper.

    @param input_text The complete source text.

    @param indicator_offset The offset of the block scalar indicator.

    @return The 0-based column of the owner, or -1.
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


def _block_scalar_body_end(input_text: str, offset: int, *, parent_indent: int) -> tuple[int, bool]:
    """
    Return the offset after the lines of a block scalar, and whether it has content.

    The content indentation n is the owner column plus the indentation width
    of the document, which only the parser knows. The lexer instead ends the
    scalar before the first line that holds a character other than space or
    TAB and is indented no deeper than the owner (parent_indent). The rules
    end it before the first such line indented less than n; a line indented
    deeper than the owner but less than n is an indentation error either
    way, and the parser reports it when it checks every line against n.
    Lines of spaces and TABs only belong to the scalar, where the parser
    checks them too.

    @param input_text The complete source text.

    @param offset The offset of the line after the header.

    @param parent_indent The 0-based column of the owner, or -1.

    @return The offset after the last line of the scalar, and whether it has content.
    """
    has_content = False

    while offset < len(input_text):
        line_start = offset
        line_end = offset

        while line_end < len(input_text) and input_text[line_end] not in "\r\n":
            line_end += 1

        line_text = input_text[line_start:line_end]

        # A '---' or '...' line at column 0 is always a document marker.
        if line_text.rstrip(" \t") in ("---", "..."):
            break

        if line_text.strip(" \t") != "":
            line_indent = len(line_text) - len(line_text.lstrip(" "))
            if line_indent <= parent_indent:
                break
            has_content = True

        offset = line_end

        if offset < len(input_text) and input_text.startswith("\r\n", offset):
            offset += 2
        elif offset < len(input_text) and input_text[offset] in "\r\n":
            offset += 1

    return offset, has_content


def _lex_single_quoted_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a single-quoted scalar, quotes included.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
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


def _reject_colon_without_space(input_text: str, offset: int, lexer_state: LexerState) -> None:
    """
    Raise a LexError for a ':' right after a value that is not followed by a space.

    A mapping colon is followed by a space, a line break or the end of the
    input, in flow context too, so JSON-style {"a":1} is an error. Without
    this check the ':1' would read as a plain scalar and the error would
    only say that a colon is missing.

    @param input_text The complete source text.

    @param offset The offset to look at.

    @param lexer_state The lexer state at the current position.
    """
    if (
        offset < len(input_text)
        and input_text[offset] == ":"
        and not _is_mapping_colon(input_text, offset)
    ):
        raise korml.error.LexError(
            message="a mapping colon must be followed by a space",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(
                _advance_position(
                    lexer_state.position,
                    input_text[lexer_state.position.offset : offset],
                )
            ),
            source_line=_source_line(input_text, lexer_state),
        )


def _validate_flow_value_boundary(
    input_text: str,
    lexer_state: LexerState,
) -> None:
    """
    Raise a LexError if what follows a value cannot follow it.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.
    """
    if lexer_state.mode is not LexerMode.FLOW_VALUE_START:
        _reject_colon_without_space(input_text, lexer_state.position.offset, lexer_state)
        return

    offset = lexer_state.position.offset

    while offset < len(input_text) and input_text[offset] in " \t\r\n":
        offset += 1

    if offset >= len(input_text):
        return

    if input_text[offset] == "#":
        return

    _reject_colon_without_space(input_text, offset, lexer_state)

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
    """
    Consume a double-quoted scalar, quotes included.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
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

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
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

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
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

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
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

        case ":" if _is_mapping_colon(input_text, position.offset):
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

        case "." if _is_marker_line(input_text, lexer_state, "..."):
            return _lex_document_end(input_text, lexer_state)

        case _:
            return _lex_plain_scalar(input_text, lexer_state)


def _lex_folded_block_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a folded block scalar.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
    _debug_lexer(lexer_state, "lex folded block scalar")

    return _lex_block_scalar(
        input_text,
        lexer_state,
        indicator=">",
        token_type=korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
    )


def _lex_literal_block_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a literal block scalar.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
    _debug_lexer(lexer_state, "lex literal block scalar")

    return _lex_block_scalar(
        input_text,
        lexer_state,
        indicator="|",
        token_type=korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
    )


def _raise_block_scalar_error(input_text: str, lexer_state: LexerState, message: str) -> None:
    """
    Raise a LexError with the code INVALID_BLOCK_SCALAR.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @param message What is wrong.
    """
    raise korml.error.LexError(
        message=message,
        code=korml.lexer.v1.ErrorCode.INVALID_BLOCK_SCALAR,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(lexer_state.position),
        source_line=_source_line(input_text, lexer_state),
    )


def _lex_block_scalar(
    input_text: str,
    lexer_state: LexerState,
    *,
    indicator: str,
    token_type: korml.lexer.v1.TokenType,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a block scalar: its header line and all its content lines.

    The header is the indicator, optionally followed by whitespace and a
    comment. YAML's chomping and indentation indicators are not part of
    korml: the value always ends with exactly one line break and the content
    indentation follows from the layout, so there is one way to write each
    block scalar. A block scalar without a content line is an error; the
    empty string is written "".

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @param indicator The indicator of the scalar, '|' or '>'.

    @param token_type The kind of token to produce.

    @return The token and the lexer state after it.
    """
    position = lexer_state.position

    if input_text[position.offset] != indicator:
        raise korml.error.BugError(
            message=f"_lex_block_scalar() called without leading {indicator!r}",
            location="korml.lexer._lex_block_scalar",
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

    offset = position.offset + 1
    header_end = offset

    while header_end < len(input_text) and input_text[header_end] not in "\r\n":
        header_end += 1

    header_rest = input_text[offset:header_end]
    header_text = header_rest.lstrip(" \t")
    is_comment = header_text.startswith("#") and len(header_text) < len(header_rest)

    if header_text != "" and not is_comment:
        _raise_block_scalar_error(
            input_text,
            lexer_state,
            f"only a comment may follow the block scalar indicator {indicator!r}; "
            "korml has no chomping or indentation indicators",
        )

    if header_end >= len(input_text):
        _raise_block_scalar_error(
            input_text,
            lexer_state,
            'block scalar has no content lines; write an empty string as ""',
        )

    offset = header_end + (2 if input_text.startswith("\r\n", header_end) else 1)

    offset, has_content = _block_scalar_body_end(
        input_text,
        offset,
        parent_indent=_block_scalar_parent_indent(input_text, position.offset),
    )

    if not has_content:
        _raise_block_scalar_error(
            input_text,
            lexer_state,
            'block scalar has no content lines; write an empty string as ""',
        )

    value = input_text[position.offset : offset]

    token, new_position = _make_token(token_type, value, position)

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

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
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

        case ":" if _is_mapping_colon(input_text, position.offset):
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
        case "." if _is_marker_line(input_text, lexer_state, "..."):
            return _lex_document_end(input_text, lexer_state)

        case _:
            return _lex_plain_scalar(input_text, lexer_state)


def _lex_flow_mapping_end(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume the '}' that closes a flow mapping.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
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
    """
    Consume the ']' that closes a flow sequence.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
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
    """
    Consume the ':' between a key and its value.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
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


def _is_mapping_colon(input_text: str, offset: int) -> bool:
    """
    Return whether the ':' at offset separates a key from its value.

    A colon is a mapping indicator only when a space, a line break or the
    end of the input follows it, in block and flow context alike. Any other
    colon belongs to a plain scalar, as in http://example.org:8080 or 12:30.

    @param input_text The complete source text.

    @param offset The offset of the colon.

    @return True if the colon is a mapping indicator.
    """
    following = offset + 1
    return following >= len(input_text) or input_text[following] in " \r\n"


def _mode_after_value(lexer_state: LexerState) -> LexerMode:
    """
    Return the lexer mode after a complete value.

    @param lexer_state The lexer state at the current position.

    @return FLOW_VALUE_START inside a flow collection, otherwise VALUE_START.
    """
    if lexer_state.flow_nesting_level > 0:
        return LexerMode.FLOW_VALUE_START

    return LexerMode.VALUE_START


def _raise_plain_scalar_error(
    input_text: str,
    lexer_state: LexerState,
    offset: int,
    message: str,
) -> None:
    """
    Raise a LexError with the code INVALID_PLAIN_SCALAR.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @param offset The offset of the problem.

    @param message What is wrong.
    """
    raise korml.error.LexError(
        message=message,
        code=korml.lexer.v1.ErrorCode.INVALID_PLAIN_SCALAR,
        source_name=lexer_state.source_file.filename,
        span=_make_error_span(
            _advance_position(
                lexer_state.position,
                input_text[lexer_state.position.offset : offset],
            )
        ),
        source_line=_source_line(input_text, lexer_state),
    )


def _plain_scalar_end(input_text: str, lexer_state: LexerState) -> int:
    """
    Return the offset where the plain scalar at the current position ends.

    A plain scalar is one line of text without TAB, '#', ',', '[', ']', '{'
    and '}', and without a ':' followed by a space or a line break. In a
    flow collection, the flow indicators and a comment end it; anywhere
    else they are errors, so that a: hello, world or value#x cannot mean
    one thing to korml and another to a reader who expects YAML or a
    comment. A TAB ends it too; the whitespace that follows is checked by
    _lex_horizontal_whitespace, where only trailing whitespace may hold a
    TAB.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The offset after the last character of the scalar, before any trailing spaces are
        removed.
    """
    offset = lexer_state.position.offset
    in_flow = lexer_state.flow_nesting_level > 0

    while offset < len(input_text):
        char = input_text[offset]

        if char in "\r\n\t":
            break

        if char == "#":
            if input_text[offset - 1] == " ":
                break

            _raise_plain_scalar_error(
                input_text,
                lexer_state,
                offset,
                "'#' is not allowed in a plain scalar; a comment needs a space before it, "
                "and a value containing '#' must be quoted",
            )

        if char in ",[]{}":
            if in_flow:
                break

            _raise_plain_scalar_error(
                input_text,
                lexer_state,
                offset,
                f"{char!r} is not allowed in a plain scalar; quote the value",
            )

        if char == ":" and _is_mapping_colon(input_text, offset):
            break

        offset += 1

    return offset


def _validate_plain_scalar(input_text: str, lexer_state: LexerState, value: str) -> None:
    """
    Raise a LexError if value cannot be a plain scalar.

    The first character must not make the text read as another token or as
    YAML syntax that korml leaves out: a quote, a block scalar indicator,
    '- ', '? ' or ': ', or a document marker. '&', '*', '!', '%', '@' and
    '`' are ordinary characters, also at the start, because korml has no
    anchors, aliases, tags or directives in a document body.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @param value The text of the scalar.
    """
    offset = lexer_state.position.offset

    if value == "":
        _raise_plain_scalar_error(input_text, lexer_state, offset, "expected plain scalar")

    if value[0] in "'\"|>":
        _raise_plain_scalar_error(
            input_text,
            lexer_state,
            offset,
            f"a plain scalar cannot start with {value[0]!r}",
        )

    if value[0] in "-?:" and (len(value) == 1 or value[1] == " "):
        _raise_plain_scalar_error(
            input_text,
            lexer_state,
            offset,
            f"a plain scalar cannot be or start with {value[0]!r} followed by a space; "
            "quote the value",
        )

    if value.startswith("---") or value.startswith("..."):
        _raise_plain_scalar_error(
            input_text,
            lexer_state,
            offset,
            f"a plain scalar cannot start with {value[:3]!r}; quote the value",
        )

    for index, char in enumerate(value):
        if char in JOINER_CHARACTER_SET:
            _raise_plain_scalar_error(
                input_text,
                lexer_state,
                offset + index,
                f"character {_describe_character(char)} is not allowed in a plain scalar; "
                "quote the value",
            )


def _lex_plain_scalar(
    input_text: str,
    lexer_state: LexerState,
) -> tuple[korml.lexer.v1.Token, LexerState]:
    """
    Consume a plain scalar, without trailing spaces.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
    _debug_lexer(lexer_state, "lex plain scalar")
    position = lexer_state.position

    offset = _plain_scalar_end(input_text, lexer_state)

    # Spaces before a comment, a colon or a flow indicator are trivia.
    value = input_text[position.offset : offset].rstrip(" ")

    _validate_plain_scalar(input_text, lexer_state, value)

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

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
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

    if not _is_marker_line(input_text, lexer_state, "---"):
        at_marker = input_text.startswith("---", position.offset)
        raise korml.error.LexError(
            message=(
                "a document start marker '---' must start at column 1 and be alone on its line"
                if at_marker
                else "expected document start marker"
            ),
            code=(
                korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER
                if at_marker
                else korml.lexer.v1.ErrorCode.MISSING_DOCUMENT_START
            ),
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
    """
    Consume a sequence dash, or a plain scalar that starts with a dash.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
    _debug_lexer(lexer_state, "lex dash at value start")

    position = lexer_state.position

    if _is_marker_line(input_text, lexer_state, "---"):
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
    """
    Consume the version directive and take the language version from it.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @return The token and the lexer state after it.
    """
    _debug_lexer(lexer_state, "lex version directive")
    position = lexer_state.position
    line_text = _read_until_newline(input_text, lexer_state)

    if not line_text.startswith("%!korml"):
        raise korml.error.LexError(
            message="expected korml version directive",
            code=korml.lexer.v1.ErrorCode.MISSING_VERSION_DIRECTIVE,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    match = _VERSION_DIRECTIVE_PATTERN.fullmatch(line_text)

    if match is None or position.column != 1:
        raise korml.error.LexError(
            message=(
                "malformed version directive; write exactly '%!korml version 1.0' "
                "at the start of a line, without a comment"
            ),
            code=korml.lexer.v1.ErrorCode.INVALID_VERSION_DIRECTIVE,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(lexer_state.position),
            source_line=_source_line(input_text, lexer_state),
        )

    version_text = match.group("version")

    match version_text:
        case "1.0":
            version = korml.model.Version.v1
        case _:
            raise korml.error.LexError(
                message=f"unsupported korml version {version_text!r}; expected '1.0'",
                unquoted_message="unsupported korml version; expected '1.0'",
                code=korml.lexer.v1.ErrorCode.INVALID_VERSION_DIRECTIVE,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(lexer_state.position),
                source_line=_source_line(input_text, lexer_state),
            )

    value = line_text[: match.end("version")]

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

    @param input_text Complete source text being lexed.

    @param lexer_state Current lexer state. The current position must point to the beginning of a
        newline sequence.

    @return A tuple containing the produced NEWLINE token and the updated lexer state after
        consuming the newline.
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


def _reject_tab_separator(
    input_text: str,
    lexer_state: LexerState,
    *,
    value: str,
    end: int,
) -> None:
    """
    Raise a LexError if a TAB in whitespace is not trailing whitespace.

    A TAB has no defined width, so it may not indent a line, whose
    indentation decides the structure, and it may not separate tokens or
    sit inside a plain scalar either. Whitespace that ends the line or
    comes before a comment may hold TABs.

    @param input_text The complete source text.

    @param lexer_state The lexer state at the current position.

    @param value The whitespace.

    @param end The offset after the whitespace.
    """
    if "\t" not in value:
        return

    if end >= len(input_text) or input_text[end] in "\r\n#":
        return

    if lexer_state.position.column == 1:
        message = "tabs are not allowed in indentation; indent with spaces"
    else:
        message = "a tab cannot separate tokens or appear in a plain scalar; use spaces"

    raise korml.error.LexError(
        message=message,
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

    @param input_text Complete source text being lexed.

    @param lexer_state Current lexer state. The current position must point to a space or tab
        character.

    @return A tuple containing the produced WHITESPACE token and the updated lexer state after
        consuming the whitespace.
    """
    position = lexer_state.position
    offset = position.offset

    while offset < len(input_text) and input_text[offset] in " \t":
        offset += 1

    value = input_text[position.offset : offset]

    _reject_tab_separator(input_text, lexer_state, value=value, end=offset)

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

    @param input_text Complete source text being lexed.

    @param lexer_state Current lexer state. The current position must point to the '#' character
        that begins the comment.

    @return A tuple containing the produced COMMENT token and the updated lexer state after
        consuming the comment text.
    """
    position = lexer_state.position
    offset = position.offset

    # A '#' starts a comment only at the start of a line's content or after
    # whitespace; "a"#b is not a value followed by a comment.
    if offset > 0 and input_text[offset - 1] not in " \t\r\n":
        raise korml.error.LexError(
            message="a comment must be preceded by a space",
            code=korml.lexer.v1.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=lexer_state.source_file.filename,
            span=_make_error_span(position),
            source_line=_source_line(input_text, lexer_state),
        )

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
    """
    Raise a BugError located at the current position.

    @param message What went wrong.

    @param lexer_state The lexer state at the current position.

    @param location Where in korml it went wrong.

    @param details More about the failure, if there is more.
    """
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
    """
    Print the token just read on standard error, if tracing is on.

    @param old_state The lexer state before the token.

    @param token The token.

    @param new_state The lexer state after it.
    """
    if not old_state.debug:
        return

    print(
        "[lexer-result] "
        f"token={token.type.name} "
        f"value={token.value!r} "
        f"mode={old_state.mode.value}->{new_state.mode.value}\n",
        file=sys.stderr,
    )
