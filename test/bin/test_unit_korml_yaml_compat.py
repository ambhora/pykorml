# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""
Sources that must mean the same in korml v0 as in YAML, or be rejected.

The one documented divergence: a plain scalar may start with '&', '*', '!',
'%', '@' or '`', which YAML reads as an anchor, alias, tag, directive or
reserved indicator; korml has none of those and reads them as text.
"""

import pytest

import korml
import korml.lexer.file


def _load(source: str) -> object:
    return korml.loads(source).to_builtin()[0]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("url: http://example.org:8080/a\n", {"url": "http://example.org:8080/a"}),
        ("time: 12:30\n", {"time": "12:30"}),
        ("win: C:\\path\n", {"win": "C:\\path"}),
        ("ipv6: ::1\n", {"ipv6": "::1"}),
        ("a: x:y\n", {"a": "x:y"}),
        ("key: value # comment\n", {"key": "value"}),
        ('{"a": 1}\n', {"a": "1"}),
        ("{a: http://x:80}\n", {"a": "http://x:80"}),
    ],
)
def test_colon_and_hash_inside_plain_scalars(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize(
    "source",
    ["link: http://x.org/page#top\n", "key: value#x # comment\n", '{"a":1}\n', "{a: 1,b:2}\n"],
)
def test_hash_without_space_and_colon_without_space_are_errors(source: str) -> None:
    with pytest.raises(korml.KormlError):
        korml.loads(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: hello, world\n", None),
        ("a: x[1]\n", None),
        ("a: x]\n", None),
        ("a: {b}x\n", None),
        ("- a, b\n", None),
        ("a: 'hello, world'\n", {"a": "hello, world"}),
        ("[a, b]\n", ["a", "b"]),
    ],
)
def test_flow_indicators_inside_block_plain_scalars(source: str, expected: object) -> None:
    if expected is None:
        with pytest.raises(korml.KormlError):
            _load(source)
        return
    assert _load(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: |\n  x\n\n  y\nb: z\n", {"a": "x\n\ny\n", "b": "z"}),
        ("a: >\n  x\n  y\n\n  z\nb: w\n", {"a": "x y\nz\n", "b": "w"}),
        ("- |\n  x\n- y\n", ["x\n", "y"]),
        ("- key: |\n    x\n  next: 1\n", [{"key": "x\n", "next": "1"}]),
    ],
)
def test_block_scalar_ends_at_the_indentation_of_its_parent(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "a: |\nb: x\n",
        "a: |\n\nb: x\n",
        "a: >\n\nb: x\n",
        "a:\n  b: |\n  c: 1\n",
        "- key: |\n  next: 1\n",
    ],
)
def test_empty_block_scalars_are_errors(source: str) -> None:
    # YAML reads an empty string here; korml requires at least one content
    # line and writes the empty string "".
    with pytest.raises(korml.LexError, match="no content lines"):
        korml.loads(source)


@pytest.mark.parametrize(
    "source",
    ["[a, b]: 1\n", "{a: 1} x\n", "- a\n-b\n", "a:\n  - x\n  y\n"],
)
def test_content_outside_every_node_is_an_error(source: str) -> None:
    with pytest.raises(korml.ParseError, match="unexpected content"):
        korml.loads(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: &x 1\n", {"a": "&x 1"}),
        ("b: *x\n", {"b": "*x"}),
        ("a: !!str 1\n", {"a": "!!str 1"}),
        ("a: %x\n", {"a": "%x"}),
        ("a: @x\n", {"a": "@x"}),
        ("a: `x\n", {"a": "`x"}),
        ("[&a]\n", ["&a"]),
    ],
)
def test_yaml_node_indicators_are_text_in_korml(source: str, expected: object) -> None:
    # The documented divergence from YAML: korml has no anchors, aliases,
    # tags or directives in a body, so these characters are ordinary text.
    assert _load(source) == expected


@pytest.mark.parametrize("source", ["? a\n: b\n", "a: ? x\n", "[? a]\n"])
def test_complex_mapping_keys_are_errors(source: str) -> None:
    with pytest.raises(korml.LexError, match="'\\?' followed by a space"):
        korml.loads(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [("a: ?x\n", {"a": "?x"}), ("a: x&y*z!\n", {"a": "x&y*z!"})],
)
def test_indicators_inside_plain_scalars_are_text(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize("source", ["a: 1\na: 2\n", "{a: 1, a: 2}\n", "x:\n  b: 1\n  b: 2\n"])
def test_duplicate_keys_are_errors(source: str) -> None:
    with pytest.raises(korml.ParseError, match="duplicate mapping key 'a'|'b'"):
        korml.loads(source)


@pytest.mark.parametrize(
    "source",
    [
        "[" * 5000 + "]" * 5000,
        "".join("  " * i + f"k{i}:\n" for i in range(200)) + "  " * 200 + "v\n",
    ],
    ids=["flow", "block"],
)
def test_deep_nesting_is_a_parse_error(source: str) -> None:
    with pytest.raises(korml.ParseError, match="nested deeper than 128"):
        korml.loads(source)


def test_nesting_up_to_the_limit_is_accepted() -> None:
    source = "[" * 128 + "]" * 128
    assert korml.loads(source).to_builtin()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('a: "x\\u0041"\n', {"a": "xA"}),
        ('a: "\\u0041\\U0001F600"\n', {"a": "A\U0001f600"}),
        ('a: "\\u0085\\u00a0\\u2028\\u2029\\u001B"\n', {"a": "\x85\xa0\u2028\u2029\x1b"}),
        ('a: "\\b\\f\\n\\r\\t"\n', {"a": "\b\f\n\r\t"}),
        ('a: "\\\\\\/\\""\n', {"a": '\\/"'}),
    ],
)
def test_double_quoted_escapes(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        'a: "\\q"\n',
        'a: "\\x41"\n',
        'a: "\\0"\n',
        'a: "\\e"\n',
        'a: "\\N"\n',
        'a: "\\ "\n',
        'a: "\\u004"\n',
        'a: "\\ud800"\n',
        'a: "\\U00110000"\n',
    ],
)
def test_invalid_double_quoted_escapes_are_errors(source: str) -> None:
    with pytest.raises(korml.ParseError, match="escape"):
        korml.loads(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [("a: 'it''s'\n", {"a": "it's"}), ("a: ''''\n", {"a": "'"}), ("['a''b', c]\n", ["a'b", "c"])],
)
def test_doubled_single_quote_is_an_escaped_quote(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize("source", ["a:\n\t- x\n", "a:\n \tb: 1\n", "[a,\n\tb]\n"])
def test_tabs_in_indentation_are_errors(source: str) -> None:
    with pytest.raises(korml.LexError, match="tabs are not allowed in indentation"):
        korml.loads(source)


@pytest.mark.parametrize("source", ["a:\t1\n", "a: x\ty\n", "[a,\tb]\n", "- a\n-\tb\n"])
def test_tabs_between_tokens_are_errors(source: str) -> None:
    with pytest.raises(korml.LexError, match="tab"):
        korml.loads(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: x\t# c\n", {"a": "x"}),
        ("a: x\t\n", {"a": "x"}),
        ("\t# comment\na: 1\n", {"a": "1"}),
        ("a: 'x\ty'\n", {"a": "x\ty"}),
        ('a: "x\ty"\n', {"a": "x\ty"}),
        ("a: |\n  x\ty\n", {"a": "x\ty\n"}),
    ],
)
def test_tabs_in_trailing_whitespace_comments_and_quotes_are_allowed(
    source: str, expected: object
) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize(
    "source",
    ["\ufeffa: 1\n", "\ufeff%!korml version 1.0\n---\na: 1\n...\n", "a: 'x\ufeffy'\n"],
)
def test_byte_order_mark_is_an_error(source: str) -> None:
    with pytest.raises(korml.LexError, match="BYTE ORDER MARK"):
        korml.loads(source)


def test_lexer_rejects_text_with_a_byte_order_mark() -> None:
    with pytest.raises(korml.LexError, match="BYTE ORDER MARK"):
        korml.lexer.file.lex("<test>", "\ufeffa: 1\n")
