# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import dataclasses
import typing

import pytest

import korml
import korml.core
import korml.error
import korml.lexer.v1
import korml.lexer.v1.file

SOURCE_NAME = "<unit-test>"


def _position(
    *,
    line: int = 1,
    column: int = 1,
    offset: int = 0,
) -> korml.core.Position:
    return korml.core.Position(
        line=line,
        column=column,
        offset=offset,
    )


def _state(
    source: str,
    *,
    mode: korml.lexer.v1.file.LexerMode = korml.lexer.v1.file.LexerMode.VALUE_START,
    offset: int = 0,
    line: int = 1,
    column: int = 1,
    flow_nesting_level: int = 0,
    version: korml.Version = korml.Version.v1,
    debug: bool = False,
) -> korml.lexer.v1.file.LexerState:
    return korml.lexer.v1.file.LexerState(
        mode=mode,
        position=_position(
            line=line,
            column=column,
            offset=offset,
        ),
        flow_nesting_level=flow_nesting_level,
        source_file=korml.lexer.v1.file.SourceFile(
            filename=SOURCE_NAME,
            value=source,
        ),
        version=version,
        debug=debug,
    )


def _assert_bug_error(
    callback: typing.Callable[[], object],
    expected_message: str,
) -> None:
    with pytest.raises(korml.error.BugError) as error_info:
        callback()

    assert expected_message in str(error_info.value)


def _assert_lex_error(
    callback: typing.Callable[[], object],
    expected_message: str,
) -> None:
    with pytest.raises(korml.error.LexError) as error_info:
        callback()

    assert expected_message in str(error_info.value)


def test_debug_output_from_public_lex(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = "%!korml version 1.0\n---\nkey: value\n"

    korml.lexer.v1.file.lex(SOURCE_NAME, source, debug=True)

    captured = capsys.readouterr()

    assert "[lexer-debug]" in captured.out
    assert "[lexer-result]" in captured.out
    assert "start lexing" in captured.out
    assert "token=VERSION_DIRECTIVE" in captured.out


def test_debug_lexer_at_end_of_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = "abc"

    state = _state(
        source,
        offset=len(source),
        column=len(source) + 1,
        debug=True,
    )

    korml.lexer.v1.file._debug_lexer(state, "end of input")

    captured = capsys.readouterr()

    assert "[lexer-debug]" in captured.out
    assert "char=None" in captured.out
    assert "end of input" in captured.out


def test_debug_lexer_result_no_output_when_debug_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = ","
    state = _state(source, debug=False)

    token, new_position = korml.lexer.v1.file._make_token(
        korml.lexer.v1.TokenType.FLOW_SEPARATOR,
        ",",
        state.position,
    )

    new_state = dataclasses.replace(
        state,
        position=new_position,
    )

    korml.lexer.v1.file._debug_lexer_result(state, token, new_state)

    captured = capsys.readouterr()

    assert captured.out == ""


@pytest.mark.parametrize(
    ("function", "source", "mode", "expected_message"),
    [
        (
            korml.lexer.v1.file._lex_flow_entry_separator,
            "x",
            korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
            "_lex_flow_entry_separator() called without leading ','",
        ),
        (
            korml.lexer.v1.file._lex_document_end,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_document_end() called without leading '...'",
        ),
        (
            korml.lexer.v1.file._lex_single_quoted_scalar,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_single_quoted_scalar() called without leading single quote",
        ),
        (
            korml.lexer.v1.file._lex_double_quoted_scalar,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_double_quoted_scalar() called without leading double quote",
        ),
        (
            korml.lexer.v1.file._lex_flow_sequence_start,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_flow_sequence_start() called without leading '['",
        ),
        (
            korml.lexer.v1.file._lex_flow_mapping_start,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_flow_mapping_start() called without leading '{'",
        ),
        (
            korml.lexer.v1.file._lex_folded_block_scalar,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_folded_block_scalar() called without leading '>'",
        ),
        (
            korml.lexer.v1.file._lex_literal_block_scalar,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_literal_block_scalar() called without leading '|'",
        ),
        (
            korml.lexer.v1.file._lex_flow_mapping_end,
            "x",
            korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
            "_lex_flow_mapping_end() called without leading '}'",
        ),
        (
            korml.lexer.v1.file._lex_flow_sequence_end,
            "x",
            korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
            "_lex_flow_sequence_end() called without leading ']'",
        ),
        (
            korml.lexer.v1.file._lex_colon,
            "x",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            "_lex_colon() called without leading ':'",
        ),
    ],
)
def test_private_lexer_helpers_reject_wrong_leading_character(
    function: typing.Callable[[str, korml.lexer.v1.file.LexerState], object],
    source: str,
    mode: korml.lexer.v1.file.LexerMode,
    expected_message: str,
) -> None:
    state = _state(
        source,
        mode=mode,
    )

    _assert_bug_error(
        lambda: function(source, state),
        expected_message,
    )


def test_lex_value_start_token_rejects_wrong_mode() -> None:
    source = "value"
    state = _state(
        source,
        mode=korml.lexer.v1.file.LexerMode.STREAM,
    )

    _assert_bug_error(
        lambda: korml.lexer.v1.file._lex_value_start_token(source, state),
        "_lex_value_start_token() called outside VALUE_START mode",
    )


def test_lex_flow_value_start_token_rejects_wrong_mode() -> None:
    source = "value"
    state = _state(
        source,
        mode=korml.lexer.v1.file.LexerMode.VALUE_START,
    )

    _assert_bug_error(
        lambda: korml.lexer.v1.file._lex_flow_value_start_token(source, state),
        "_lex_flow_value_start_token() called outside FLOW_VALUE_START mode",
    )


def test_lex_stream_token_rejects_wrong_mode() -> None:
    source = "---"
    state = _state(
        source,
        mode=korml.lexer.v1.file.LexerMode.VALUE_START,
    )

    _assert_bug_error(
        lambda: korml.lexer.v1.file._lex_stream_token(source, state),
        "_lex_stream_token() called outside STREAM mode",
    )


def test_flow_mapping_end_rejects_negative_flow_nesting_level() -> None:
    source = "}"
    state = _state(
        source,
        mode=korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
        flow_nesting_level=0,
    )

    _assert_lex_error(
        lambda: korml.lexer.v1.file._lex_flow_mapping_end(source, state),
        "unexpected flow mapping end",
    )


def test_flow_sequence_end_rejects_negative_flow_nesting_level() -> None:
    source = "]"
    state = _state(
        source,
        mode=korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
        flow_nesting_level=0,
    )

    _assert_lex_error(
        lambda: korml.lexer.v1.file._lex_flow_sequence_end(source, state),
        "unexpected flow sequence end",
    )


def test_raise_lexer_bug() -> None:
    source = "abc"
    state = _state(source)

    _assert_bug_error(
        lambda: korml.lexer.v1.file._raise_lexer_bug(
            message="synthetic lexer bug",
            lexer_state=state,
            location="test.location",
            details="extra details",
        ),
        "synthetic lexer bug",
    )


def test_public_lex_rejects_unsupported_internal_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_lexer_state_type = korml.lexer.v1.file.LexerState

    class UnsupportedMode:
        def __repr__(self) -> str:
            return "UnsupportedMode()"

    def make_lexer_state(
        *,
        mode: korml.lexer.v1.file.LexerMode,
        position: korml.core.Position,
        flow_nesting_level: int,
        source_file: korml.lexer.v1.file.SourceFile,
        version: korml.Version = korml.Version.unknown,
        debug: bool = False,
    ) -> korml.lexer.v1.file.LexerState:
        return original_lexer_state_type(
            mode=UnsupportedMode(),  # type: ignore[arg-type]
            position=position,
            flow_nesting_level=flow_nesting_level,
            source_file=source_file,
            version=korml.Version.v1,
            debug=debug,
        )

    monkeypatch.setattr(
        korml.lexer.v1.file,
        "LexerState",
        make_lexer_state,
    )

    _assert_bug_error(
        lambda: korml.lexer.v1.file.lex(SOURCE_NAME, "x"),
        "unsupported lexer mode in lex()",
    )


@pytest.mark.parametrize(
    ("source", "mode", "flow_nesting_level", "expected_token_type"),
    [
        (
            ",",
            korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
            1,
            korml.lexer.v1.TokenType.FLOW_SEPARATOR,
        ),
        (
            "...",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            0,
            korml.lexer.v1.TokenType.DOC_END,
        ),
        (
            "'value'",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            0,
            korml.lexer.v1.TokenType.SQ_SCALAR,
        ),
        (
            '"value"',
            korml.lexer.v1.file.LexerMode.VALUE_START,
            0,
            korml.lexer.v1.TokenType.DQ_SCALAR,
        ),
        (
            "[",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            0,
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
        ),
        (
            "{",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            0,
            korml.lexer.v1.TokenType.FLOW_MAPPING_START,
        ),
        (
            ":",
            korml.lexer.v1.file.LexerMode.VALUE_START,
            0,
            korml.lexer.v1.TokenType.COLON,
        ),
        (
            "]",
            korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
            1,
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
        ),
        (
            "}",
            korml.lexer.v1.file.LexerMode.FLOW_VALUE_START,
            1,
            korml.lexer.v1.TokenType.FLOW_MAPPING_END,
        ),
    ],
)
def test_private_lexer_helpers_accept_expected_leading_character(
    source: str,
    mode: korml.lexer.v1.file.LexerMode,
    flow_nesting_level: int,
    expected_token_type: korml.lexer.v1.TokenType,
) -> None:
    state = _state(
        source,
        mode=mode,
        flow_nesting_level=flow_nesting_level,
    )

    if source == ",":
        token, _ = korml.lexer.v1.file._lex_flow_entry_separator(source, state)
    elif source == "...":
        token, _ = korml.lexer.v1.file._lex_document_end(source, state)
    elif source.startswith("'"):
        token, _ = korml.lexer.v1.file._lex_single_quoted_scalar(source, state)
    elif source.startswith('"'):
        token, _ = korml.lexer.v1.file._lex_double_quoted_scalar(source, state)
    elif source == "[":
        token, _ = korml.lexer.v1.file._lex_flow_sequence_start(source, state)
    elif source == "{":
        token, _ = korml.lexer.v1.file._lex_flow_mapping_start(source, state)
    elif source == ":":
        token, _ = korml.lexer.v1.file._lex_colon(source, state)
    elif source == "]":
        token, _ = korml.lexer.v1.file._lex_flow_sequence_end(source, state)
    elif source == "}":
        token, _ = korml.lexer.v1.file._lex_flow_mapping_end(source, state)
    else:
        raise AssertionError(f"unsupported source in test: {source!r}")

    assert token.type is expected_token_type
    assert token.value == source


def test_make_error_span_is_empty() -> None:
    position = _position(
        line=3,
        column=7,
        offset=20,
    )

    span = korml.lexer.v1.file._make_error_span(position)

    assert span.start == position
    assert span.end == position


def test_read_until_newline_handles_crlf() -> None:
    source = "abc\r\ndef"
    state = _state(source)

    assert korml.lexer.v1.file._read_until_newline(source, state) == "abc"


def test_unlex_roundtrip() -> None:
    source = "%!korml version 1.0\n---\nkey: value\n"

    file = korml.lexer.v1.file.lex(SOURCE_NAME, source)

    assert korml.lexer.v1.file.unlex(file) == source
