# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import pytest

import korml
import korml.lexer.v0.file
import korml.parser.v0

SOURCE_NAME = "<test>"


def test_parse_v0_single_implicit_document() -> None:
    file = korml.lexer.v0.file.lex(SOURCE_NAME, "a: b\n")

    stream = korml.parser.v0.parse(file)

    assert stream.version is korml.Version.v0
    assert stream.to_builtin() == [{"a": "b"}]
    assert stream.token_array == file.token_array


def test_parse_v0_blank_source_as_one_empty_document() -> None:
    file = korml.lexer.v0.file.lex(SOURCE_NAME, "# comment\n\n")

    stream = korml.parser.v0.parse(file)

    assert stream.version is korml.Version.v0
    assert isinstance(stream[0], korml.Empty)
    assert stream[0].token_array == file.token_array
    assert stream.to_builtin() == [None]


def test_parse_v0_rejects_v1_file() -> None:
    file = korml.lexer.v0.File(
        token_array=(),
        version=korml.Version.v1,
        filename=SOURCE_NAME,
    )

    with pytest.raises(ValueError, match="parser v0 cannot parse"):
        korml.parser.v0.parse(file)
