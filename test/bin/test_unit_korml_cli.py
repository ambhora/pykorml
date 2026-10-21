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
