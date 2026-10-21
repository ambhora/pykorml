# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import pytest

import korml
import korml.core
import korml.lexer.v1
import korml.parser.v1


def _make_token_array(
    *spec_array: tuple[korml.lexer.v1.TokenType, str],
) -> tuple[korml.lexer.v1.Token, ...]:
    return korml.lexer.v1.make_token_array(
        *spec_array,
        start=korml.core.make_position(
            line=1,
            column=1,
            offset=0,
        ),
    )


def test_parse_scalar_parses_plain_scalar_and_preserves_cst() -> None:
    token_array = _make_token_array((korml.lexer.v1.TokenType.PLAIN_SCALAR, "hello"))

    scalar = korml.parser.v1._parse_scalar(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert scalar == korml.Scalar[korml.lexer.v1.Token]("hello")
    assert scalar.value == "hello"
    assert scalar.version is korml.Version.v1
    assert scalar.token_array == token_array
    assert scalar.source == "hello"


def test_parse_scalar_ignores_trivia_for_semantic_shape_but_preserves_cst() -> None:
    token_array = _make_token_array(
        (korml.lexer.v1.TokenType.WHITESPACE, "  "),
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "hello"),
        (korml.lexer.v1.TokenType.COMMENT, "# comment"),
        (korml.lexer.v1.TokenType.NEWLINE, "\n"),
    )

    scalar = korml.parser.v1._parse_scalar(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert scalar.value == "hello"
    assert scalar.token_array == token_array
    assert scalar.source == "  hello# comment\n"


def test_parse_scalar_parses_single_quoted_scalar() -> None:
    token_array = _make_token_array((korml.lexer.v1.TokenType.SQ_SCALAR, "'hello'"))

    scalar = korml.parser.v1._parse_scalar(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert scalar.value == "hello"


def test_parse_scalar_parses_double_quoted_scalar() -> None:
    token_array = _make_token_array((korml.lexer.v1.TokenType.DQ_SCALAR, '"hello \\"Jayesh\\""'))

    scalar = korml.parser.v1._parse_scalar(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert scalar.value == 'hello "Jayesh"'


def test_parse_scalar_parses_literal_block_scalar() -> None:
    token_array = _make_token_array(
        (korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR, "|\n  hello\n  world\n")
    )

    scalar = korml.parser.v1._parse_scalar(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert scalar.value == "hello\nworld\n"


def test_parse_scalar_parses_folded_block_scalar() -> None:
    token_array = _make_token_array(
        (korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR, ">\n  hello\n  world\n")
    )

    scalar = korml.parser.v1._parse_scalar(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
    )

    assert scalar.value == "hello world\n"


def test_parse_scalar_rejects_empty_token_array() -> None:
    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_scalar(
            (),
            version=korml.Version.v1,
            source_name="<test>",
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_SCALAR)


def test_parse_scalar_rejects_non_scalar_token() -> None:
    token_array = _make_token_array((korml.lexer.v1.TokenType.DOC_START, "---"))

    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_scalar(
            token_array,
            version=korml.Version.v1,
            source_name="<test>",
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_SCALAR)


def test_parse_scalar_rejects_multiple_scalar_tokens() -> None:
    token_array = _make_token_array(
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "first"),
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "second"),
    )

    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_scalar(
            token_array,
            version=korml.Version.v1,
            source_name="<test>",
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_SCALAR)


def _lex_body(source: str) -> tuple[korml.lexer.v1.Token, ...]:
    file = korml.lexer.v1.file.lex(
        "<test>",
        f"%!korml version 1.0\n---\n{source}\n...\n",
    )

    return file.token_array[4:-2]


def test_parse_value_dispatches_to_plain_scalar() -> None:
    token_array = _lex_body("hello")

    value = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(value, korml.Scalar)
    assert value.to_builtin() == "hello"


def test_parse_sequence_parses_scalar_items() -> None:
    token_array = _lex_body("- first\n- second")

    sequence = korml.parser.v1._parse_sequence(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert sequence.style is korml.Style.block
    assert sequence.to_builtin() == ["first", "second"]
    assert sequence.token_array == tuple(token_array)


def test_parse_value_dispatches_to_sequence() -> None:
    token_array = _lex_body("- first\n- second")

    value = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(value, korml.Sequence)
    assert value.to_builtin() == ["first", "second"]


def test_parse_sequence_parses_nested_sequence_on_same_line() -> None:
    token_array = _lex_body("- - first\n  - second")

    sequence = korml.parser.v1._parse_sequence(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert sequence.to_builtin() == [["first", "second"]]


def test_parse_sequence_preserves_comments_in_container_cst() -> None:
    source = "- first\n# comment\n- second"
    token_array = _lex_body(source)

    sequence = korml.parser.v1._parse_sequence(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert sequence.to_builtin() == ["first", "second"]
    assert "# comment" in sequence.source


def test_parse_mapping_parses_scalar_values() -> None:
    token_array = _lex_body("first: one\nsecond: two")

    mapping = korml.parser.v1._parse_mapping(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert mapping.style is korml.Style.block
    assert mapping.to_builtin() == {
        "first": "one",
        "second": "two",
    }
    assert mapping.token_array == tuple(token_array)


def test_parse_value_dispatches_to_mapping() -> None:
    token_array = _lex_body("first: one\nsecond: two")

    value = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(value, korml.Mapping)
    assert value.to_builtin() == {
        "first": "one",
        "second": "two",
    }


def test_parse_mapping_parses_sequence_value() -> None:
    token_array = _lex_body("items:\n- first\n- second")

    mapping = korml.parser.v1._parse_mapping(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert mapping.to_builtin() == {
        "items": ["first", "second"],
    }


def test_parse_mapping_parses_nested_mapping_value() -> None:
    token_array = _lex_body("parent:\n  child: value")

    mapping = korml.parser.v1._parse_mapping(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert mapping.to_builtin() == {
        "parent": {
            "child": "value",
        },
    }


def test_parse_mapping_parses_single_quoted_key() -> None:
    token_array = _lex_body("'quoted key': value")

    mapping = korml.parser.v1._parse_mapping(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert mapping.to_builtin() == {
        "quoted key": "value",
    }


def test_parse_sequence_rejects_non_sequence_tokens() -> None:
    token_array = _lex_body("key: value")

    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_sequence(
            token_array,
            version=korml.Version.v1,
            source_name="<test>",
            depth=0,
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_SEQUENCE)


def test_parse_mapping_rejects_non_mapping_tokens() -> None:
    token_array = _lex_body("value")

    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_mapping(
            token_array,
            version=korml.Version.v1,
            source_name="<test>",
            depth=0,
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_MAPPING)


def test_parse_value_rejects_empty_tokens() -> None:
    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_value(
            (),
            version=korml.Version.v1,
            source_name="<test>",
            depth=0,
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_VALUE)


def test_parse_sequence_rejects_item_without_value() -> None:
    token_array = _lex_body("-")

    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_sequence(
            token_array,
            version=korml.Version.v1,
            source_name="<test>",
            depth=0,
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_VALUE)


def test_parse_file_parses_single_document_mapping() -> None:
    file = korml.lexer.v1.file.lex(
        "<test>",
        "%!korml version 1.0\n---\na: b\n...\n",
    )

    stream = korml.parser.v1.parse(file)

    assert stream.version is korml.Version.v1
    assert stream.filename == "<test>"
    assert stream.token_array == file.token_array
    assert stream.to_builtin() == [{"a": "b"}]


def test_parse_file_parses_multiple_documents() -> None:
    file = korml.lexer.v1.file.lex(
        "<test>",
        "%!korml version 1.0\n---\none\n...\n---\ntwo\n...\n",
    )

    stream = korml.parser.v1.parse(file)

    assert stream.to_builtin() == ["one", "two"]


def test_parse_flow_sequence() -> None:
    token_array = _lex_body('[a, "b", {c: d}]')

    sequence = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(sequence, korml.Sequence)
    assert sequence.style is korml.Style.flow
    assert sequence.to_builtin() == ["a", "b", {"c": "d"}]


def test_parse_flow_sequence_parses_empty_sequence() -> None:
    token_array = _lex_body("[]")

    sequence = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(sequence, korml.Sequence)
    assert sequence.style is korml.Style.flow
    assert sequence.to_builtin() == []


def test_parse_flow_mapping() -> None:
    token_array = _lex_body('{a: b, "nested": [c, d]}')

    mapping = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(mapping, korml.Mapping)
    assert mapping.style is korml.Style.flow
    assert mapping.to_builtin() == {
        "a": "b",
        "nested": ["c", "d"],
    }


def test_parse_flow_mapping_parses_empty_mapping() -> None:
    token_array = _lex_body("{}")

    mapping = korml.parser.v1._parse_value(
        token_array,
        version=korml.Version.v1,
        source_name="<test>",
        depth=0,
    )

    assert isinstance(mapping, korml.Mapping)
    assert mapping.style is korml.Style.flow
    assert mapping.to_builtin() == {}


def test_parse_flow_mapping_rejects_entry_without_colon() -> None:
    token_array = _lex_body("{a}")

    with pytest.raises(korml.ParseError) as error_info:
        korml.parser.v1._parse_value(
            token_array,
            version=korml.Version.v1,
            source_name="<test>",
            depth=0,
        )

    assert error_info.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_MAPPING_COLON)


@pytest.mark.parametrize("source", ["[a,,b]", "[,a]", "[,]", "{a: 1,, b: 2}", "{,a: b}", "{,}"])
@pytest.mark.parametrize("version", [0, 1])
def test_flow_rejects_missing_entries(source: str, version: int) -> None:
    text = f"%!korml version 1.0\n---\n{source}\n...\n" if version else source
    with pytest.raises(korml.ParseError) as exc:
        korml.loads(text)
    assert exc.value.code() == str(korml.parser.v1.ErrorCode.EXPECTED_VALUE)
    assert exc.value.span is not None


@pytest.mark.parametrize("source, expected", [
    ("[a,]", [["a"]]),
    ("{a: b,}", [{"a": "b"}]),
    ("[]", [[]]),
    ("{}", [{}]),
    ("[a, [b,],]", [["a", ["b"]]]),
])
def test_flow_accepts_empty_collection_and_trailing_comma(source: str, expected: list) -> None:
    assert korml.loads(source).to_builtin() == expected
