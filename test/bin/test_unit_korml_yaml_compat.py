# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""Sources that must mean the same in korml v0 as in YAML, or be rejected."""

import pytest

import korml


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
        ("link: http://x.org/page#top\n", {"link": "http://x.org/page#top"}),
        ("key: value#x # comment\n", {"key": "value#x"}),
        ('{"a":1}\n', {"a": "1"}),
        ("{a: http://x:80}\n", {"a": "http://x:80"}),
    ],
)
def test_colon_and_hash_inside_plain_scalars(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a: hello, world\n", {"a": "hello, world"}),
        ("a: x[1]\n", {"a": "x[1]"}),
        ("a: {b}x\n", None),
        ("- a, b\n", ["a, b"]),
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
        ("a: |\nb: x\n", {"a": "", "b": "x"}),
        ("a: |\n\nb: x\n", {"a": "", "b": "x"}),
        ("a: >\n\nb: x\n", {"a": "", "b": "x"}),
        ("a: |\n  x\n\n  y\nb: z\n", {"a": "x\n\ny\n", "b": "z"}),
        ("a:\n  b: |\n  c: 1\n", {"a": {"b": "", "c": "1"}}),
        ("- key: |\n  next: 1\n", [{"key": "", "next": "1"}]),
        ("- |\n  x\n- y\n", ["x\n", "y"]),
    ],
)
def test_block_scalar_ends_at_the_indentation_of_its_parent(source: str, expected: object) -> None:
    assert _load(source) == expected


@pytest.mark.parametrize(
    "source",
    ["[a, b]: 1\n", "{a: 1} x\n", "- a\n-b\n", "a:\n  - x\n  y\n"],
)
def test_content_outside_every_node_is_an_error(source: str) -> None:
    with pytest.raises(korml.ParseError, match="unexpected content"):
        korml.loads(source)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("a: &x 1\n", "anchors"),
        ("b: *x\n", "aliases"),
        ("a: !!str 1\n", "tags"),
        ("? a\n: b\n", "complex mapping keys"),
        ("a: %x\n", "directives"),
        ("a: @x\n", "reserved"),
        ("[&a]\n", "anchors"),
    ],
)
def test_excluded_yaml_features_are_errors(source: str, message: str) -> None:
    with pytest.raises(korml.LexError, match=message):
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
