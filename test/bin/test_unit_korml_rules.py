# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""
One accepted and one rejected source for each rule of the Korml rules.

The tests are grouped by the section of the rules they check. A source is
loaded as v0 unless it starts with the v1 directive; _v1 wraps a body in a
one-document v1 stream.
"""

import pytest

import korml
import korml.lexer.file
import korml.lexer.v0.file
import korml.lexer.v1.file


def _v1(body: str) -> str:
    return f"%!korml version 1.0\n---\n{body}...\n"


def _load(source: str) -> object:
    return korml.loads(source).to_builtin()


def _load_root(source: str) -> object:
    return _load(source)[0]


def _assert_error(source: str, code: str) -> korml.KormlError:
    with pytest.raises(korml.KormlError) as error_info:
        korml.loads(source)

    assert error_info.value.code() == code, error_info.value
    return error_info.value


# --------------------------------------------------------------------------------------------------
# 1. Source text
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "char",
    [
        "\x00",
        "\x07",
        "\x1b",
        "\x7f",
        "\x85",
        "\x9f",
        "\ufffe",
        "\uffff",
        "\u2028",
        "\u2029",
        "\ufeff",
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202e",
        "\u2066",
        "\u2069",
        "\u200b",
        "\u2060",
    ],
)
@pytest.mark.parametrize("place", ["a: 'x{}'\n", "a: x # c{}\n", "a: |\n  x{}\n"])
def test_forbidden_characters_are_errors_everywhere(char: str, place: str) -> None:
    error = _assert_error(place.format(char), "INVALID_CHARACTER")

    assert f"U+{ord(char):04X}" in error.message()


@pytest.mark.parametrize("char", ["\x00", "\x1b", "\x85", "\u2028", "\ufeff", "\u200b", "\u2060"])
def test_forbidden_characters_may_be_written_as_escapes(char: str) -> None:
    assert _load_root(f'a: "\\u{ord(char):04x}"\n') == {"a": char}


def test_lone_surrogate_is_an_error() -> None:
    error = _assert_error("a: 'x\ud800'\n", "INVALID_CHARACTER")

    assert "U+D800" in error.message()


def test_byte_order_mark_is_an_error_at_the_start_and_inside() -> None:
    _assert_error("\ufeffa: 1\n", "INVALID_CHARACTER")
    _assert_error("a: 1\nb: '\ufeff'\n", "INVALID_CHARACTER")


@pytest.mark.parametrize("source", ["a: 1\nb: 2\n", "a: 1\r\nb: 2\r\n", "a: 1\r\nb: 2"])
def test_one_line_break_style_throughout_is_accepted(source: str) -> None:
    assert _load_root(source) == {"a": "1", "b": "2"}


@pytest.mark.parametrize("source", ["a: 1\r\nb: 2\n", "a: 1\nb: 2\r\n", "# c\r\n\na: 1\n"])
def test_mixed_line_breaks_are_errors(source: str) -> None:
    _assert_error(source, "INVALID_LINE_BREAK")


@pytest.mark.parametrize("source", ["a: 1\rb: 2\n", "a: 1\r", "# c\r\na: 1\r"])
def test_lone_carriage_return_is_an_error(source: str) -> None:
    _assert_error(source, "INVALID_LINE_BREAK")


def test_final_line_break_is_optional() -> None:
    assert _load_root("a: 1") == _load_root("a: 1\n") == {"a": "1"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x: 'a\u200cb'\n", {"x": "a\u200cb"}),
        ('x: "a\u200db"\n', {"x": "a\u200db"}),
        ("x: |\n  a\u200cb\n", {"x": "a\u200cb\n"}),
        ("x: 1 # a\u200db\n", {"x": "1"}),
        ('"a\\u200cb": 1\n', {"a\u200cb": "1"}),
    ],
)
def test_joiners_are_allowed_raw_in_quoted_values_block_scalars_and_comments(
    source: str, expected: object
) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("x: a\u200cb\n", "INVALID_PLAIN_SCALAR"),
        ("a\u200db: 1\n", "INVALID_PLAIN_SCALAR"),
        ("'a\u200cb': 1\n", "INVALID_KEY"),
        ('"a\u200db": 1\n', "INVALID_KEY"),
        ("{'a\u200db': 1}\n", "INVALID_KEY"),
    ],
)
def test_joiners_are_errors_raw_in_plain_scalars_and_keys(source: str, code: str) -> None:
    _assert_error(source, code)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: x\t\n", {"a": "x"}),
        ("a: x \t # c\t\n", {"a": "x"}),
        ("a: 'x\ty'\n", {"a": "x\ty"}),
        ("a: |\n  \tx\n", {"a": "\tx\n"}),
        ("a: 1\n\t\nb: 2\n", {"a": "1", "b": "2"}),
    ],
)
def test_tabs_where_they_are_permitted(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    "source",
    ["a:\n\tb: 1\n", "a: x\ty\n", "a\t: 1\n", "[a,\tb]\n", "-\ta\n", "a: [x,\n\ty]\n"],
)
def test_tabs_in_indentation_scalars_and_between_tokens_are_errors(source: str) -> None:
    _assert_error(source, "UNEXPECTED_CHARACTER")


# --------------------------------------------------------------------------------------------------
# 2. Lines, comments, blank lines
# --------------------------------------------------------------------------------------------------


def test_comments_and_blank_lines_at_any_indentation_take_no_part_in_layout() -> None:
    source = "a:\n# c\n      # c\n\n   \n  b: 1\n"

    assert _load_root(source) == {"a": {"b": "1"}}


@pytest.mark.parametrize("source", ['a: "x"#c\n', "a: [x]#c\n", "a: x#c\n"])
def test_comment_needs_whitespace_before_it(source: str) -> None:
    with pytest.raises(korml.LexError):
        korml.loads(source)


# --------------------------------------------------------------------------------------------------
# 3. Layout
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a:\n b:\n  c: 1\n", {"a": {"b": {"c": "1"}}}),
        ("a:\n    b:\n        c: 1\n", {"a": {"b": {"c": "1"}}}),
        ("a:\n   - x\n   - y\n", {"a": ["x", "y"]}),
    ],
)
def test_indentation_width_is_inferred_once_per_document(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    "source",
    ["a:\n  b:\n     c: 1\n", "a:\n   b: 1\nc:\n  d: 2\n", "a:\n    b:\n      c: 1\n"],
)
def test_every_level_indents_by_the_same_width(source: str) -> None:
    _assert_error(source, "INVALID_INDENTATION")


def test_width_is_per_document_in_a_stream() -> None:
    source = "%!korml version 1.0\n---\na:\n  b: 1\n...\n---\na:\n    b: 1\n...\n"

    assert _load(source) == [{"a": {"b": "1"}}, {"a": {"b": "1"}}]


def test_dedent_to_an_open_level_is_accepted() -> None:
    assert _load_root("a:\n  b:\n    c: 1\nd: 2\n") == {"a": {"b": {"c": "1"}}, "d": "2"}


def test_dedent_to_a_column_that_is_not_open_is_an_error() -> None:
    _assert_error("a:\n    b:\n        c: 1\n  d: 2\n", "INVALID_INDENTATION")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("- key: v\n  key2: v2\n", [{"key": "v", "key2": "v2"}]),
        ("- - a\n  - b\n- c\n", [["a", "b"], "c"]),
        ("- - - a\n    - b\n", [[["a", "b"]]]),
        ("- a:\n    b: 1\n", [{"a": {"b": "1"}}]),
        ("- |\n  text\n", ["text\n"]),
        ("-\n  a: 1\n", [{"a": "1"}]),
        ("- # comment\n  a: 1\n", [{"a": "1"}]),
    ],
)
def test_compact_entries(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    "source",
    ["-  a\n", "- key: v\n key2: v2\n", "- key: v\n   key2: v2\n", "- a:\n  b: 1\n"],
)
def test_compact_entry_content_starts_two_columns_after_the_dash(source: str) -> None:
    with pytest.raises(korml.ParseError):
        korml.loads(source)


def test_compact_level_does_not_set_the_width() -> None:
    # The compact level of 'a' is two columns right of the dash; the first
    # indented line, four columns deeper than 'a', sets w = 4.
    source = "- a:\n      b: 1\n- c:\n      d: 2\n"

    assert _load_root(source) == [{"a": {"b": "1"}}, {"c": {"d": "2"}}]
    _assert_error("- a:\n      b: 1\n- c:\n    d: 2\n", "INVALID_INDENTATION")


def test_sequence_under_a_key_is_indented() -> None:
    assert _load_root("key:\n  - a\n") == {"key": ["a"]}


def test_zero_indented_sequence_is_an_error() -> None:
    _assert_error("key:\n- a\n", "EXPECTED_VALUE")


def test_root_starts_at_column_zero() -> None:
    _assert_error("  a: 1\n", "INVALID_INDENTATION")


# --------------------------------------------------------------------------------------------------
# 4. Tokens: the colon
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('{"a": 1}\n', {"a": "1"}),
        ("{a: 1, b: 2}\n", {"a": "1", "b": "2"}),
        ("a   : 1\n", {"a": "1"}),
        ("a:\n  b: 1\n", {"a": {"b": "1"}}),
        ("a: http://x:8080\n", {"a": "http://x:8080"}),
        ("[a:b, c:]\n", ["a:b", "c:"]),
    ],
)
def test_colon_followed_by_space_line_break_or_end_is_an_indicator(
    source: str, expected: object
) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize("source", ['{"a":1}\n', "'a':1\n", '["a":1]\n'])
def test_colon_after_a_quoted_key_needs_a_space(source: str) -> None:
    with pytest.raises(korml.LexError, match="followed by a space"):
        korml.loads(source)


@pytest.mark.parametrize("source", ["{a:1}\n", "a:1\nb: 2\n"])
def test_colon_without_space_is_part_of_a_plain_scalar(source: str) -> None:
    with pytest.raises(korml.ParseError):
        korml.loads(source)


# --------------------------------------------------------------------------------------------------
# 5. Scalars
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: x  y\n", {"a": "x  y"}),
        ("a: -5\n", {"a": "-5"}),
        ("a: -x\n", {"a": "-x"}),
        ("a: ?x\n", {"a": "?x"}),
        ("a: :x\n", {"a": ":x"}),
        ("a: &x\n", {"a": "&x"}),
        ("a: *x\n", {"a": "*x"}),
        ("a: !x\n", {"a": "!x"}),
        ("a: %x\n", {"a": "%x"}),
        ("a: @x\n", {"a": "@x"}),
        ("a: `x\n", {"a": "`x"}),
        ("a: x'y\"z\\n\n", {"a": "x'y\"z\\n"}),
        ("a: --\n", {"a": "--"}),
        ("a: ..\n", {"a": ".."}),
        ("a: .x\n", {"a": ".x"}),
        ("&anchor: 1\n", {"&anchor": "1"}),
    ],
)
def test_plain_scalars(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "a: x,y\n",
        "a: x[1]\n",
        "a: x]\n",
        "a: x{y\n",
        "a: x}\n",
        "a: x#y\n",
        "a: ? x\n",
        "a: ?\n",
        "[?]\n",
        "[- x]\n",
        "[-]\n",
        "a: ---\n",
        "a: ---x\n",
        "a: ...\n",
        "a: ...x\n",
        "[...]\n",
        "a, b: 1\n",
    ],
)
def test_plain_scalar_errors(source: str) -> None:
    with pytest.raises(korml.LexError):
        korml.loads(source)


def test_plain_scalar_cannot_start_with_a_dash_followed_by_a_space() -> None:
    # In block context '- x' is a sequence entry, which cannot follow a key
    # on its line.
    _assert_error("a: - x\n", "EXPECTED_VALUE")


@pytest.mark.parametrize(
    ("source", "expected"),
    [("a: 'it''s'\n", {"a": "it's"}), ("a: 'x\\n'\n", {"a": "x\\n"}), ("a: ''\n", {"a": ""})],
)
def test_single_quoted_scalars(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize("source", ["a: 'x\ny'\n", "a: 'x\n"])
def test_single_quoted_scalars_are_single_line(source: str) -> None:
    with pytest.raises(korml.LexError):
        korml.loads(source)


@pytest.mark.parametrize(
    ("escape", "value"),
    [
        ('\\"', '"'),
        ("\\\\", "\\"),
        ("\\/", "/"),
        ("\\b", "\b"),
        ("\\f", "\f"),
        ("\\n", "\n"),
        ("\\r", "\r"),
        ("\\t", "\t"),
        ("\\u00e9", "é"),
        ("\\u00E9", "é"),
        ("\\U0001F600", "\U0001f600"),
        ("\\U0010ffff", "\U0010ffff"),
    ],
)
def test_double_quoted_escapes(escape: str, value: str) -> None:
    assert _load_root(f'a: "{escape}"\n') == {"a": value}


@pytest.mark.parametrize(
    "escape",
    [
        "\\0",
        "\\a",
        "\\e",
        "\\v",
        "\\x41",
        "\\N",
        "\\_",
        "\\L",
        "\\P",
        "\\ ",
        "\\\t",
        "\\'",
        "\\u12",
        "\\U0001F60",
        "\\ud800",
        "\\uDFFF",
        "\\U0000D800",
        "\\U00110000",
    ],
)
def test_other_double_quoted_escapes_are_errors(escape: str) -> None:
    _assert_error(f'a: "{escape}"\n', "INVALID_ESCAPE")


@pytest.mark.parametrize("source", ['a: "x\ny"\n', 'a: "x\n'])
def test_double_quoted_scalars_are_single_line(source: str) -> None:
    with pytest.raises(korml.LexError):
        korml.loads(source)


def test_key_of_1024_characters_is_accepted() -> None:
    key = "k" * 1024

    assert _load_root(f"{key}: 1\n") == {key: "1"}
    assert _load_root(f'"{key[:1022]}": 1\n') == {key[:1022]: "1"}


@pytest.mark.parametrize(
    "source", ["k" * 1025 + ": 1\n", '"' + "k" * 1023 + '": 1\n', "{" + "k" * 1025 + ": 1}\n"]
)
def test_key_longer_than_1024_characters_is_an_error(source: str) -> None:
    _assert_error(source, "INVALID_KEY")


@pytest.mark.parametrize(
    "source",
    ["a: 1\n'a': 2\n", 'a: 1\n"a": 2\n', "{a: 1, 'a': 2}\n", '"\\u0061": 1\na: 2\n'],
)
def test_keys_are_compared_as_decoded_strings(source: str) -> None:
    _assert_error(source, "DUPLICATE_KEY")


def test_keys_are_not_normalized() -> None:
    assert _load_root('"\\u00e9": 1\n"e\\u0301": 2\n') == {"é": "1", "e\u0301": "2"}


# --------------------------------------------------------------------------------------------------
# 6. Block scalars
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: |\n  x\n", {"a": "x\n"}),
        ("- |\n  x\n", ["x\n"]),
        ("- a: >\n    x\n", [{"a": "x\n"}]),
        ("a: | # comment\n  x\n", {"a": "x\n"}),
        ("a: |\t\n  x\n", {"a": "x\n"}),
    ],
)
def test_block_scalar_positions_and_headers(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("|\n  x\n", "EXPECTED_VALUE"),
        ("[|\n  x]\n", "UNEXPECTED_CHARACTER"),
        ("a: |-\n  x\n", "INVALID_BLOCK_SCALAR"),
        ("a: |+\n  x\n", "INVALID_BLOCK_SCALAR"),
        ("a: >-\n  x\n", "INVALID_BLOCK_SCALAR"),
        ("a: |2\n  x\n", "INVALID_BLOCK_SCALAR"),
        ("a: | x\n  y\n", "INVALID_BLOCK_SCALAR"),
        ("a: |#c\n  y\n", "INVALID_BLOCK_SCALAR"),
        ("a: |", "INVALID_BLOCK_SCALAR"),
        ("a: |\nb: 1\n", "INVALID_BLOCK_SCALAR"),
        ("a: |\n\n   \nb: 1\n", "INVALID_BLOCK_SCALAR"),
    ],
)
def test_block_scalar_position_and_header_errors(source: str, code: str) -> None:
    _assert_error(source, code)


def test_block_scalar_content_indentation_is_owner_plus_width() -> None:
    assert _load_root("a:\n    b: |\n        x\n") == {"a": {"b": "x\n"}}
    assert _load_root("a: |\n   x\nb:\n   c: 1\n") == {"a": "x\n", "b": {"c": "1"}}


@pytest.mark.parametrize(
    "source",
    [
        "a:\n    b: |\n      x\n",
        "a: |\n   x\nb:\n  c: 1\n",
        "a: |\n    x\n  y\n",
        "a: |\n   x\n  y\n",
    ],
)
def test_block_scalar_content_indented_wrongly_is_an_error(source: str) -> None:
    with pytest.raises(korml.KormlError):
        korml.loads(source)


def test_first_block_scalar_line_has_exactly_the_content_indentation() -> None:
    _assert_error("a:\n  b: 1\nc: |\n    x\n", "INVALID_BLOCK_SCALAR")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: |\n  x\n   y\n  z\n", "x\n y\nz\n"),
        ("a: |\n\n  x\n", "\nx\n"),
        ("a: |\n  x\n\n\n  y\n", "x\n\n\ny\n"),
        ("a: |\n  x\n\n\n", "x\n"),
        ("a: |\n  x  \n", "x  \n"),
        ("a: |\n  x\t\n", "x\t\n"),
        ("a: |\n  # not a comment\n", "# not a comment\n"),
        ("a: |\r\n  x\r\n  y\r\n", "x\ny\n"),
        ("a: |\n  x\n \n  y\n", "x\n\ny\n"),
        ("a: |\n  x", "x\n"),
    ],
)
def test_literal_block_scalar_values(source: str, expected: str) -> None:
    assert _load_root(source) == {"a": expected}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: >\n  x\n  y\n", "x y\n"),
        ("a: >\n  x\n\n  y\n", "x\ny\n"),
        ("a: >\n  x\n\n\n  y\n", "x\n\ny\n"),
        ("a: >\n\n  x\n", "\nx\n"),
        ("a: >\n  x  \n  y\n", "x   y\n"),
        ("a: >\n  x\n\n", "x\n"),
        ("a: >\r\n  x\r\n  y\r\n", "x y\n"),
    ],
)
def test_folded_block_scalar_values(source: str, expected: str) -> None:
    assert _load_root(source) == {"a": expected}


@pytest.mark.parametrize("source", ["a: >\n  x\n    y\n", "a: >\n  x\n  \ty\n"])
def test_folded_block_scalar_lines_must_not_be_more_indented(source: str) -> None:
    _assert_error(source, "INVALID_BLOCK_SCALAR")


@pytest.mark.parametrize(
    "source", ["a: |\n  x\n     \nb: 1\n", "a: |\n  x\n \t\n", "a: |\n  x\n\t\n  y\n"]
)
def test_block_scalar_whitespace_lines_too_long_or_with_tabs_are_errors(source: str) -> None:
    _assert_error(source, "INVALID_BLOCK_SCALAR")


def test_block_scalar_ends_before_a_less_indented_line() -> None:
    assert _load_root("a: |\n  x\n# comment\nb: 1\n") == {"a": "x\n", "b": "1"}


def test_document_markers_end_a_block_scalar() -> None:
    assert _load(_v1("a: |\n  x\n")) == [{"a": "x\n"}]


# --------------------------------------------------------------------------------------------------
# 7. Flow collections
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("[]\n", []),
        ("{}\n", {}),
        ("[a, [b], {c: d}]\n", ["a", ["b"], {"c": "d"}]),
        ("[a,\n b]\n", ["a", "b"]),
        ("k: [a,\n  b]\n", {"k": ["a", "b"]}),
        ("k: [a,  # c\n\n  # c\n  b\n  ]\n", {"k": ["a", "b"]}),
        ("- [a,\n   b]\n", [["a", "b"]]),
        ("k: {a: 1,\n  b: 2}\n", {"k": {"a": "1", "b": "2"}}),
        ("k: [a\n  , b]\n", {"k": ["a", "b"]}),
    ],
)
def test_flow_collections(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("[a, ]\n", "EXPECTED_VALUE"),
        ("[a,]\n", "EXPECTED_VALUE"),
        ("{a: 1,}\n", "EXPECTED_VALUE"),
        ("[, a]\n", "EXPECTED_VALUE"),
        ("[a,, b]\n", "EXPECTED_VALUE"),
        ("[a: b]\n", "UNEXPECTED_CONTENT"),
        ("k: [a,\nb]\n", "INVALID_INDENTATION"),
        ("- [a,\nb]\n", "INVALID_INDENTATION"),
        ("{a\n  : 1}\n", "UNEXPECTED_CONTENT"),
        ("{a:\n  1}\n", "UNEXPECTED_CONTENT"),
        ("k: [a] b\n", "UNEXPECTED_CONTENT"),
        ("{[a]: b}\n", "EXPECTED_SCALAR"),
    ],
)
def test_flow_collection_errors(source: str, code: str) -> None:
    _assert_error(source, code)


# --------------------------------------------------------------------------------------------------
# 8. Grammar
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [("x\n", "x"), ("[x]\n", ["x"]), ("'x'\n", "x"), ("a: 1\n", {"a": "1"})],
)
def test_root_nodes(source: str, expected: object) -> None:
    assert _load_root(source) == expected


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("key:\n  value\n", "EXPECTED_VALUE"),
        ("key:\n  [a]\n", "EXPECTED_VALUE"),
        ("-\n  value\n", "EXPECTED_VALUE"),
        ("key:\nnext: 1\n", "EXPECTED_VALUE"),
        ("a: b: c\n", "UNEXPECTED_CONTENT"),
        ("x\ny\n", "UNEXPECTED_CONTENT"),
        ("- a\nb: 1\n", "UNEXPECTED_CONTENT"),
        ("a: 1\n- b\n", "UNEXPECTED_CONTENT"),
    ],
)
def test_grammar_errors(source: str, code: str) -> None:
    _assert_error(source, code)


def test_empty_v0_source_is_an_empty_document() -> None:
    assert _load("") == []
    assert _load("# only a comment\n\n") == []


# --------------------------------------------------------------------------------------------------
# 9. v1 stream
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "%!korml version 1.0\n---\na: 1\n...\n",
        "# c\n\n%!korml version 1.0\n---\na: 1\n...\n",
        "%!korml version 1.0 \t\n# c\n\n---\na: 1\n... \n# c\n",
        "%!korml version 1.0\n---\t\na: 1\n...",
        "%!korml version 1.0\r\n---\r\na: 1\r\n...\r\n",
    ],
)
def test_v1_stream_framing(source: str) -> None:
    assert _load(source) == [{"a": "1"}]


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("%!korml version 1.0\n", "MISSING_DOCUMENT_START"),
        ("%!korml version 1.0\n---\na: 1\n", "MISSING_DOCUMENT_END"),
        ("%!korml version 1.0\n---\na: 1\n...\n---\nb: 1\n", "MISSING_DOCUMENT_END"),
        ("%!korml version 1.0 # c\n---\n...\n", "INVALID_VERSION_DIRECTIVE"),
        ("%!korml  version 1.0\n---\n...\n", "INVALID_VERSION_DIRECTIVE"),
        ("%!korml\tversion 1.0\n---\n...\n", "INVALID_VERSION_DIRECTIVE"),
        ("%!korml version 1.1\n---\n...\n", "INVALID_VERSION_DIRECTIVE"),
        ("%!korml version 2.0\n---\n...\n", "INVALID_VERSION_DIRECTIVE"),
        ("%!korml version 1.0x\n---\n...\n", "INVALID_VERSION_DIRECTIVE"),
        ("%!korml version 1.0\n--- # c\n...\n", "UNEXPECTED_CHARACTER"),
        ("%!korml version 1.0\n--- a\n...\n", "UNEXPECTED_CHARACTER"),
        ("%!korml version 1.0\n ---\n...\n", "UNEXPECTED_CHARACTER"),
        ("%!korml version 1.0\n---\n... # c\n", "INVALID_PLAIN_SCALAR"),
        ("%!korml version 1.0\n---\n...x\n", "INVALID_PLAIN_SCALAR"),
        ("%!korml version 1.0\n---\na: 1\n---\n...\n", "UNEXPECTED_CHARACTER"),
        ("%!korml version 1.0\n---\n...\nx\n", "MISSING_DOCUMENT_START"),
    ],
)
def test_v1_stream_framing_errors(source: str, code: str) -> None:
    _assert_error(source, code)


def test_indented_directive_makes_the_source_v0() -> None:
    assert korml.lexer.file.detect_version(" %!korml version 1.0\n") is korml.Version.v0
    assert korml.lexer.file.detect_version("# c\n%!korml version 1.0\n") is korml.Version.v1

    with pytest.raises(korml.LexError, match="version directive"):
        korml.loads("  %!korml version 1.0\n---\n...\n")


def test_empty_document_is_valid() -> None:
    # The model has no way to hold a document without a root, so the stream
    # lists only the documents that have one.
    assert _load("%!korml version 1.0\n---\n...\n") == []
    assert _load("%!korml version 1.0\n---\na: 1\n...\n---\n# c\n...\n") == [{"a": "1"}]


def test_document_markers_inside_flow_and_block_scalars() -> None:
    _assert_error("%!korml version 1.0\n---\nk: [a,\n...\n", "UNEXPECTED_CHARACTER")
    assert _load(_v1("k: |\n  ...\n  ---\n")) == [{"k": "...\n---\n"}]


# --------------------------------------------------------------------------------------------------
# 10. v0 and version detection
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["---\na: 1\n", "a: 1\n...\n", "a: 1\n--- \t\n", "...\n"])
def test_v0_document_markers_are_errors(source: str) -> None:
    with pytest.raises(korml.LexError):
        korml.lexer.v0.file.lex("<test>", source)


def test_v0_text_that_starts_like_a_marker_is_a_plain_scalar_error() -> None:
    with pytest.raises(korml.LexError, match="cannot start with '---'"):
        korml.loads("a: --- x\n")


# --------------------------------------------------------------------------------------------------
# 12. Limits
# --------------------------------------------------------------------------------------------------


def test_nesting_depth_of_at_least_64_is_supported() -> None:
    block = "".join("  " * level + f"k{level}:\n" for level in range(64)) + "  " * 64 + "k: v\n"

    assert korml.loads(block).to_builtin()
    assert korml.loads("[" * 64 + "]" * 64).to_builtin()
    assert korml.loads("- " * 64 + "x\n").to_builtin()


def test_nesting_beyond_the_limit_is_an_error() -> None:
    _assert_error("- " * 200 + "x\n", "TOO_DEEP")
