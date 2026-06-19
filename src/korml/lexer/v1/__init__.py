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
    WHITESPACE = "WHITESPACE"
    COMMENT = "COMMENT"
    NEWLINE = "NEWLINE"
    EOF = "EOF"

    VERSION_DIRECTIVE = "VERSION_DIRECTIVE"
    DOC_START = "DOC_START"
    DOC_END = "DOC_END"

    DASH_ITEM = "DASH_ITEM"
    COLON = "COLON"

    LITERAL_BLOCK_SCALAR = "LITERAL_BLOCK_SCALAR"
    FOLDED_BLOCK_SCALAR = "FOLDED_BLOCK_SCALAR"

    FLOW_SEQUENCE_START = "FLOW_SEQUENCE_START"
    FLOW_SEQUENCE_END = "FLOW_SEQUENCE_END"
    FLOW_MAPPING_START = "FLOW_MAPPING_START"
    FLOW_MAPPING_END = "FLOW_MAPPING_END"
    FLOW_SEPARATOR = "FLOW_SEPARATOR"

    SQ_SCALAR = "SQ_SCALAR"
    DQ_SCALAR = "DQ_SCALAR"
    PLAIN_SCALAR = "PLAIN_SCALAR"


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: str
    span: korml.core.Span

    def to_dict(self) -> dict[str, object]:
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
    version: korml.model.Version
    filename: str


class ErrorCode(str, enum.Enum):
    MISSING_VERSION_DIRECTIVE = "MISSING_VERSION_DIRECTIVE"
    INVALID_VERSION_DIRECTIVE = "INVALID_VERSION_DIRECTIVE"
    MISSING_DOCUMENT_START = "MISSING_DOCUMENT_START"
    MISSING_DOCUMENT_END = "MISSING_DOCUMENT_END"
    UNMATCHED_DOC_START = "UNMATCHED_DOC_START"
    UNMATCHED_DOC_END = "UNMATCHED_DOC_END"
    UNEXPECTED_CHARACTER = "UNEXPECTED_CHARACTER"

    def __str__(self) -> str:
        return self.value


def make_token(
    *,
    type: TokenType,
    value: str,
    start: korml.core.Position,
) -> Token:
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
    token_array: list[Token] = []
    position = start

    for type, value in spec_array:
        token = make_token(type=type, value=value, start=position)

        token_array.append(token)
        position = token.span.end

    return tuple(token_array)
