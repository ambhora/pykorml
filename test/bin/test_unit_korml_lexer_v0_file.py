# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import pytest

import korml
import korml.lexer.file
import korml.lexer.v0.file

SOURCE_NAME = "<test>"


def test_lex_v0_mapping_without_version_directive_or_document_markers() -> None:
    file = korml.lexer.v0.file.lex(SOURCE_NAME, "a: b\n")

    assert file.version is korml.Version.v0
    assert korml.lexer.v0.file.unlex(file) == "a: b\n"
    assert [token.type for token in file.token_array] == [
        korml.lexer.v0.TokenType.PLAIN_SCALAR,
        korml.lexer.v0.TokenType.COLON,
        korml.lexer.v0.TokenType.WHITESPACE,
        korml.lexer.v0.TokenType.PLAIN_SCALAR,
        korml.lexer.v0.TokenType.NEWLINE,
    ]
    assert file.token_array[0].span.start.line == 1
    assert file.token_array[0].span.start.column == 1


def test_version_dispatching_lexer_detects_v0_without_header() -> None:
    file = korml.lexer.file.lex(SOURCE_NAME, "a: b\n")

    assert file.version is korml.Version.v0


def test_version_dispatching_lexer_detects_v1_with_header() -> None:
    file = korml.lexer.file.lex(SOURCE_NAME, "%!korml version 1.0\n---\na: b\n...\n")

    assert file.version is korml.Version.v1


def test_lex_v0_rejects_version_directive() -> None:
    with pytest.raises(korml.LexError, match="version directive"):
        korml.lexer.v0.file.lex(SOURCE_NAME, "%!korml version 1.0\n---\na: b\n")


def test_lex_v0_rejects_document_start_marker() -> None:
    with pytest.raises(korml.LexError, match="document start"):
        korml.lexer.v0.file.lex(SOURCE_NAME, "---\na: b\n")


def test_lex_v0_rejects_document_end_marker() -> None:
    with pytest.raises(korml.LexError, match="document stream markers"):
        korml.lexer.v0.file.lex(SOURCE_NAME, "a: b\n...\n")
