# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""How errors describe where they are."""

import pytest

import korml


def test_lex_error_quotes_the_whole_line_with_the_caret_under_the_error() -> None:
    with pytest.raises(korml.LexError) as exc_info:
        korml.loads('a: "x\n', filename="app.korml")

    lines = str(exc_info.value).splitlines()

    assert lines[1] == "  --> app.korml:1:4"
    assert lines[3] == '1 | a: "x'
    assert lines[4] == "  |    ^"


def test_bug_error_keeps_the_message_method() -> None:
    error = korml.error.BugError(message="broken", location="here")

    assert error.message().startswith("internal bug at here: broken")
    assert error.summary == "broken"


def test_lexer_debug_output_goes_to_standard_error(capsys: pytest.CaptureFixture[str]) -> None:
    korml.loads("a: 1\n", debug=True)

    captured = capsys.readouterr()

    assert captured.out == ""
    assert "[lexer-debug]" in captured.err


def test_schema_errors_are_korml_errors() -> None:
    with pytest.raises(korml.KormlError) as exc_info:
        korml.schema.compile_schema({"schema": "other"})

    assert isinstance(exc_info.value, korml.schema.SchemaError)
    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.code() == "INVALID_SCHEMA"


def test_bare_carriage_return_starts_a_new_line() -> None:
    with pytest.raises(korml.LexError) as exc_info:
        korml.loads('a: 1\rb: "x\n')

    assert exc_info.value.span().start.line == 2
    assert exc_info.value.span().start.column == 4


@pytest.mark.parametrize(
    ("source", "line", "column"),
    [
        ("a: 1\na: 2\n", 2, 1),
        ("[a, b]: 1\n", 1, 7),
        ("a:\n  - x\n  y\n", 3, 3),
        ('a: "\\q"\n', 1, 4),
    ],
)
def test_parse_error_names_its_position(source: str, line: int, column: int) -> None:
    with pytest.raises(korml.ParseError) as exc_info:
        korml.loads(source, filename="app.korml")

    span = exc_info.value.span()

    assert (span.start.line, span.start.column) == (line, column)
    assert f"--> app.korml:{line}:{column}" in str(exc_info.value)
    assert exc_info.value.structured()["span"]["start"]["line"] == line


def test_errors_can_be_described_without_quoting_the_source() -> None:
    with pytest.raises(korml.LexError) as exc_info:
        korml.loads('password: "hunter2\n', filename="app.korml")

    quoted = exc_info.value.describe(quote_source=True)
    unquoted = exc_info.value.describe(quote_source=False)

    assert "hunter2" in quoted
    assert quoted == str(exc_info.value)
    assert "hunter2" not in unquoted
    assert "--> app.korml:1:11" in unquoted


def test_bug_error_quotes_its_source_line_only_on_request() -> None:
    error = korml.error.BugError(message="broken", location="here", source_line="secret: x")

    assert "secret: x" in error.describe(quote_source=True)
    assert "secret: x" not in error.describe(quote_source=False)
    assert "secret: x" not in error.message()
