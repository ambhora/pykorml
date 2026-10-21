# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""The korml command line."""

import pathlib
import sys

import pytest

import korml.cli
import korml.cli.lex


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["korml", *argv])
    return korml.cli.main()


def test_internal_error_exits_with_status_70(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "a.korml"
    source.write_text("a: 1\n", encoding="utf-8")

    def explode(args: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(korml.cli.lex, "run", explode)

    assert _run(monkeypatch, "lex", "--input", str(source)) == 70
    assert "KORML BUG REPORT" in capsys.readouterr().err


def test_invalid_usage_exits_with_status_2(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run(monkeypatch, "lex")

    assert exc_info.value.code == 2


def test_lex_reads_and_writes_utf8(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "a.korml"
    source.write_bytes("name: café\n".encode())
    output = tmp_path / "tokens.txt"

    status = _run(
        monkeypatch,
        "lex",
        "--input",
        str(source),
        "--output",
        str(output),
        "--output-format",
        "text",
    )

    assert status == 0
    assert "PLAIN_SCALAR\t'café'" in output.read_bytes().decode("utf-8")


def test_input_that_is_not_utf8_is_a_user_error(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "a.korml"
    source.write_bytes(b"name: caf\xe9\n")

    assert _run(monkeypatch, "lex", "--input", str(source)) == 1
    assert "not valid UTF-8 at byte 9" in capsys.readouterr().err


def test_missing_input_is_a_user_error(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.korml"

    assert _run(monkeypatch, "lex", "--input", str(missing)) == 1
    assert f"error: {missing}: No such file or directory" in capsys.readouterr().err
