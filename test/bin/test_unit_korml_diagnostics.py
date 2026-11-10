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


def test_lone_carriage_return_is_an_error_at_its_position() -> None:
    with pytest.raises(korml.LexError) as exc_info:
        korml.loads('a: 1\rb: "x\n')

    assert exc_info.value.code() == "INVALID_LINE_BREAK"
    assert exc_info.value.span().start.line == 1
    assert exc_info.value.span().start.column == 5


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


def test_control_sequences_are_escaped_in_human_diagnostics() -> None:
    source = "%!korml version 1.0\x1b[2J\n---\nx\n...\n"
    with pytest.raises(korml.KormlError) as exc:
        korml.loads(source, filename="evil\x1b[1K.korml")

    text = str(exc.value)
    assert "\x1b" not in text
    assert r"\x1b" in text
    assert "evil" in text


def test_control_characters_in_source_line_keep_caret_aligned() -> None:
    from korml.core import Span, make_position

    span = Span(
        start=make_position(line=1, column=3, offset=2),
        end=make_position(line=1, column=4, offset=3),
    )
    error = korml.LexError(
        message="invalid token",
        source_name="input",
        span=span,
        source_line="a\x1bX",
    )
    lines = str(error).splitlines()
    assert lines[3] == r"1 | a\x1bX"
    assert lines[4] == "  | " + " " * 5 + "^"
    assert error.structured()["source_line"] == "a\x1bX"


def test_lexer_stops_at_the_token_limit() -> None:
    import korml.lexer.file

    with pytest.raises(korml.error.CompilerError, match="token count exceeds 10") as exc_info:
        korml.lexer.file.lex("<test>", "a\n" * 1000, max_tokens=10)

    assert exc_info.value.code() == "TOO_MANY_TOKENS"


def test_loads_applies_the_token_limit_while_lexing() -> None:
    with pytest.raises(korml.error.CompilerError, match="token count exceeds 100"):
        korml.loads("a\n" * 10_000, max_tokens=100)


def test_messages_keep_their_line_breaks() -> None:
    error = korml.error.BugError(message="broken", location="here", details="a\nb")

    assert "\n\nDetails:\na\nb" in str(error)


def test_source_text_in_messages_is_escaped() -> None:
    # A raw ESC is not allowed anywhere in a source; the diagnostic quotes the
    # line it is on with the control escaped.
    with pytest.raises(korml.LexError) as exc_info:
        korml.loads('a: "\\\x1b"\n')

    assert exc_info.value.code() == "INVALID_CHARACTER"
    assert "\x1b" not in str(exc_info.value)
    assert "\\x1b" in str(exc_info.value)


def test_schema_messages_escape_controls_and_keep_one_line_per_error() -> None:
    error = korml.schema.SchemaError("types.a\x1bb must be a mapping")

    assert "\x1b" not in str(error)
    assert "types.a\\x1bb must be a mapping" in str(error)


_HEADER = "%!korml version 1.0\n---\n"


@pytest.mark.parametrize(
    ("source", "secret"),
    [
        (_HEADER + "db:\n  password:\n    VDUMMY-1\n...\n", "VDUMMY-1"),
        (_HEADER + 'db:\n  password:\n    "VDUMMY-2"\n...\n', "VDUMMY-2"),
        ("db:\n  password:\n    VDUMMY-3\n", "VDUMMY-3"),
        (_HEADER + "keys:\n  - a\n|\n  VDUMMY-4\n...\n", "VDUMMY-4"),
        (_HEADER + "tokens:\n  VDUMMY-5: ci\n  VDUMMY-5: deploy\n...\n", "VDUMMY-5"),
        ("tokens:\n  VDUMMY-6: ci\n  VDUMMY-6: deploy\n", "VDUMMY-6"),
        (_HEADER + "VDUMMY-7\nVDUMMY-7b\n...\n", "VDUMMY-7"),
        (_HEADER + 'password: "VDUMMY-8" extra\n...\n', "extra"),
        (_HEADER + 'password: "\\uD800"\n...\n', "D800"),
        ("%!korml version VDUMMY-9\n---\na: 1\n...\n", "VDUMMY-9"),
    ],
)
def test_unquoted_description_leaves_document_text_out_of_the_message(
    source: str, secret: str
) -> None:
    with pytest.raises(korml.error.CompilerError) as exc_info:
        korml.loads(source, filename="app.korml")

    unquoted = exc_info.value.describe(quote_source=False)

    assert secret in exc_info.value.message()
    assert secret in str(exc_info.value)
    assert secret not in unquoted
    assert "--> app.korml:" in unquoted


_SCHEMA_SOURCE = """%!korml version 1.0
---
schema: korml.schema.v1
root:
  type: Config
types:
  Mode:
    kind: enum
    enum:
      - debug
      - release
  String:
    kind: scalar
  Config:
    kind: mapping
    fields:
      mode:
        type: Mode
      password:
        type: String
...
"""


def _schema() -> korml.schema.Schema:
    """
    Return a schema with an enum field and a string field.

    @return The schema.
    """
    return korml.schema.compile_schema(korml.loads(_SCHEMA_SOURCE).to_builtin()[0])


def test_unquoted_construction_error_leaves_document_values_out() -> None:
    value = korml.loads("mode: VDUMMY-11\nVDUMMY-12: x\npassword: ok\n").to_builtin()[0]

    with pytest.raises(korml.schema.ConstructionError) as exc_info:
        korml.schema.construct(value, _schema())

    unquoted = exc_info.value.describe(quote_source=False)

    assert "VDUMMY-11" in str(exc_info.value)
    assert "VDUMMY-12" in str(exc_info.value)
    assert unquoted.splitlines()[:2] == [
        "ConstructionError: invalid enum value for Mode",
        "unknown field",
    ]
    assert "VDUMMY" not in unquoted


def test_unquoted_construction_error_leaves_a_constructor_message_out() -> None:
    def fail(*args: object, **kwargs: object) -> object:
        """
        Fail with a message that repeats the values given.

        @param args The positional values.

        @param kwargs The keyword values.

        @return Nothing; it always raises.
        """
        raise ValueError(f"cannot use {args} {kwargs}")

    value = korml.loads("mode: debug\npassword: VDUMMY-13\n").to_builtin()[0]

    with pytest.raises(korml.schema.ConstructionError) as exc_info:
        korml.schema.construct(value, _schema(), {"Config": fail})

    assert "VDUMMY-13" in str(exc_info.value)
    assert "VDUMMY-13" not in exc_info.value.describe(quote_source=False)
    assert "a constructor raised ValueError" in exc_info.value.describe(quote_source=False)


def test_unquoted_invalid_value_error_leaves_the_path_of_document_keys_out() -> None:
    error = korml.schema.v1.InvalidValueError(
        code=korml.schema.v1.ErrorCode.TOO_DEEP, path=("VDUMMY-14",), message="too deep"
    )

    assert "VDUMMY-14" in str(error)
    assert "VDUMMY-14" not in error.describe(quote_source=False)
