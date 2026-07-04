# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""Classic in-memory lexer implementation for KORML v0.

KORML v0 is the YAML-compatible, single-document source form. It reuses the
v1 document-body tokenization rules, but starts directly in value mode and
rejects stream-level constructs such as version directives and document markers.
"""

import dataclasses
import re

import korml.core
import korml.error
from korml.lexer import v0 as lexer_v0
import korml.lexer.v1.file as v1_file
import korml.model

__all__ = ["lex", "unlex"]

_VERSION_DIRECTIVE_PATTERN = re.compile(r"%!korml\s+version\s+\d+\.\d+(?=\s*(#|$))")


def lex(filename: str, input_text: str, debug: bool = False) -> lexer_v0.File:
    """Tokenize a complete KORML v0 source string."""
    lexer_state = v1_file.LexerState(
        mode=v1_file.LexerMode.VALUE_START,
        position=korml.core.Position(1, 1, 0),
        flow_nesting_level=0,
        source_file=v1_file.SourceFile(filename, input_text),
        version=korml.model.Version.v0,
        debug=debug,
    )

    _reject_leading_version_directive(input_text, lexer_state)

    token_array: list[lexer_v0.Token] = []

    while lexer_state.position.offset < len(input_text):
        char = input_text[lexer_state.position.offset]

        if char in "\r\n":
            token, lexer_state = v1_file._lex_newline(input_text, lexer_state)
            token_array.append(token)
            continue

        if char in " \t":
            token, lexer_state = v1_file._lex_horizontal_whitespace(input_text, lexer_state)
            token_array.append(token)
            continue

        if char == "#":
            token, lexer_state = v1_file._lex_comment(input_text, lexer_state)
            token_array.append(token)
            continue

        match lexer_state.mode:
            case v1_file.LexerMode.VALUE_START:
                token, lexer_state = v1_file._lex_value_start_token(input_text, lexer_state)

            case v1_file.LexerMode.FLOW_VALUE_START:
                token, lexer_state = v1_file._lex_flow_value_start_token(input_text, lexer_state)

            case _:
                raise korml.error.BugError(
                    message="unsupported lexer mode in v0 lex()",
                    location="korml.lexer.v0.file.lex",
                    details=(
                        "v0 lexing should only use VALUE_START or "
                        f"FLOW_VALUE_START, got {lexer_state.mode!r}"
                    ),
                    source_name=filename,
                    span=_make_error_span(lexer_state.position),
                    source_line=v1_file._read_until_newline(input_text, lexer_state),
                )

        _reject_stream_token(token, input_text, lexer_state)
        token_array.append(token)

    if lexer_state.flow_nesting_level != 0:
        raise korml.error.LexError(
            message="unterminated flow collection",
            code=lexer_v0.ErrorCode.UNEXPECTED_CHARACTER,
            source_name=filename,
            span=_make_error_span(lexer_state.position),
            source_line=v1_file._read_until_newline(input_text, lexer_state),
        )

    return lexer_v0.File(
        token_array=tuple(token_array),
        version=korml.model.Version.v0,
        filename=filename,
    )


def unlex(file: lexer_v0.File) -> str:
    """Convert a tokenized KORML v0 file back to source text."""
    return "".join(token.value for token in file.token_array)


def _reject_leading_version_directive(
    input_text: str,
    lexer_state: v1_file.LexerState,
) -> None:
    line_start = 0

    while line_start < len(input_text):
        line_end = line_start
        while line_end < len(input_text) and input_text[line_end] not in "\r\n":
            line_end += 1

        line_text = input_text[line_start:line_end]
        content = line_text.lstrip(" \t")

        if content == "" or content.startswith("#"):
            line_start = _next_line_start(input_text, line_end)
            continue

        if _VERSION_DIRECTIVE_PATTERN.match(content):
            position = _position_at_offset(input_text, line_start + (len(line_text) - len(content)))
            raise korml.error.LexError(
                message="version directive is not allowed in korml v0",
                code=lexer_v0.ErrorCode.UNEXPECTED_CHARACTER,
                source_name=lexer_state.source_file.filename,
                span=_make_error_span(position),
                source_line=content,
            )

        return


def _reject_stream_token(
    token: lexer_v0.Token,
    input_text: str,
    lexer_state: v1_file.LexerState,
) -> None:
    if token.type not in {
        lexer_v0.TokenType.VERSION_DIRECTIVE,
        lexer_v0.TokenType.DOC_START,
        lexer_v0.TokenType.DOC_END,
    }:
        return

    raise korml.error.LexError(
        message="document stream markers are not allowed in korml v0",
        code=lexer_v0.ErrorCode.UNEXPECTED_CHARACTER,
        source_name=lexer_state.source_file.filename,
        span=token.span,
        source_line=v1_file._read_until_newline(input_text, lexer_state),
    )


def _next_line_start(input_text: str, line_end: int) -> int:
    if line_end < len(input_text) and input_text.startswith("\r\n", line_end):
        return line_end + 2

    if line_end < len(input_text) and input_text[line_end] in "\r\n":
        return line_end + 1

    return line_end


def _position_at_offset(input_text: str, offset: int) -> korml.core.Position:
    return korml.core.advance_position(korml.core.Position(1, 1, 0), input_text[:offset])


def _make_error_span(position: korml.core.Position) -> korml.core.Span:
    return korml.core.Span(start=position, end=position)
