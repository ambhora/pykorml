# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import dataclasses
import enum

import korml.core
import korml.model

__all__ = [
    "TokenType",
    "Token",
    "File",
    "ErrorCode",
]


class TokenType(enum.Enum):
    """The kinds of token. Every character of a source is in exactly one token."""

    WHITESPACE = "WHITESPACE"
    """A run of spaces and tabs."""
    COMMENT = "COMMENT"
    """A comment, from its '#' to the end of the line."""
    NEWLINE = "NEWLINE"
    """A line break, LF or CRLF."""
    EOF = "EOF"
    """Reserved: the lexers produce no token at the end of the input."""

    VERSION_DIRECTIVE = "VERSION_DIRECTIVE"
    """The directive '%!korml version 1.0', without trailing whitespace."""
    DOC_START = "DOC_START"
    """The document start marker '---'."""
    DOC_END = "DOC_END"
    """The document end marker '...'."""

    DASH_ITEM = "DASH_ITEM"
    """The dash of a block sequence entry."""
    COLON = "COLON"
    """The colon between a mapping key and its value."""

    LITERAL_BLOCK_SCALAR = "LITERAL_BLOCK_SCALAR"
    """A '|' scalar: its header line and all its content lines."""
    FOLDED_BLOCK_SCALAR = "FOLDED_BLOCK_SCALAR"
    """A '>' scalar: its header line and all its content lines."""

    FLOW_SEQUENCE_START = "FLOW_SEQUENCE_START"
    """The '[' that opens a flow sequence."""
    FLOW_SEQUENCE_END = "FLOW_SEQUENCE_END"
    """The ']' that closes a flow sequence."""
    FLOW_MAPPING_START = "FLOW_MAPPING_START"
    """The '{' that opens a flow mapping."""
    FLOW_MAPPING_END = "FLOW_MAPPING_END"
    """The '}' that closes a flow mapping."""
    FLOW_SEPARATOR = "FLOW_SEPARATOR"
    """The ',' between the entries of a flow collection."""

    SQ_SCALAR = "SQ_SCALAR"
    """A single-quoted scalar, quotes included."""
    DQ_SCALAR = "DQ_SCALAR"
    """A double-quoted scalar, quotes included."""
    PLAIN_SCALAR = "PLAIN_SCALAR"
    """A scalar without quotes."""


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    """A piece of source text and what it is."""

    type: TokenType
    """The kind of token."""
    value: str
    """The exact source text of the token."""
    span: korml.core.Span
    """Where the token is."""

    def to_dict(self) -> dict[str, object]:
        """Return the token as JSON-compatible data, as korml lex prints it."""
        return {
            "type": self.type.name,
            "value": self.value,
            "span": self.span.to_dict(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class File:
    """
    Tokenized representation of a korml source file.

    File is the result object produced by successful lexing. It stores the token
    stream together with source-level metadata needed by later compiler phases
    and diagnostics.
    """

    token_array: tuple[Token, ...]
    """The tokens, in source order."""
    version: korml.model.Version
    """The language version of the source."""
    filename: str
    """The name of the source."""


class ErrorCode(str, enum.Enum):
    """The codes of the errors the lexers report."""

    MISSING_VERSION_DIRECTIVE = "MISSING_VERSION_DIRECTIVE"
    """A v1 source with no '%!korml' line first."""
    INVALID_VERSION_DIRECTIVE = "INVALID_VERSION_DIRECTIVE"
    """A malformed directive, or one of an unsupported version."""
    MISSING_DOCUMENT_START = "MISSING_DOCUMENT_START"
    """A v1 document without its '---'."""
    MISSING_DOCUMENT_END = "MISSING_DOCUMENT_END"
    """A v1 document without its '...'."""
    UNMATCHED_DOC_START = "UNMATCHED_DOC_START"
    """Reserved: nothing reports this code yet."""
    UNMATCHED_DOC_END = "UNMATCHED_DOC_END"
    """Reserved: nothing reports this code yet."""
    UNEXPECTED_CHARACTER = "UNEXPECTED_CHARACTER"
    """A character that no token can start or continue with here."""
    INVALID_CHARACTER = "INVALID_CHARACTER"
    """A character the rules forbid anywhere in a source."""
    INVALID_LINE_BREAK = "INVALID_LINE_BREAK"
    """A lone CR, or LF and CRLF mixed in one source."""
    INVALID_BLOCK_SCALAR = "INVALID_BLOCK_SCALAR"
    """A block scalar with a bad header or without content."""
    INVALID_PLAIN_SCALAR = "INVALID_PLAIN_SCALAR"
    """Text that a plain scalar may not start with or hold."""

    def __str__(self) -> str:
        return self.value


def make_token(
    *,
    type: TokenType,
    value: str,
    start: korml.core.Position,
) -> Token:
    """Return the token with this type and value that starts at start."""
    return Token(
        type=type,
        value=value,
        span=korml.core.Span(
            start=start,
            end=korml.core.advance_position(start, value),
        ),
    )


def make_token_array(
    *spec_array: tuple[TokenType, str],
    start: korml.core.Position,
) -> tuple[Token, ...]:
    """Return consecutive tokens from (type, value) pairs, the first at start."""
    token_array: list[Token] = []
    position = start

    for type, value in spec_array:
        token = make_token(type=type, value=value, start=position)

        token_array.append(token)
        position = token.span.end

    return tuple(token_array)
