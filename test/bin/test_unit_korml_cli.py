# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""The korml command line."""

import pathlib
import sys

import pytest

import korml.cli
import korml.cli.bugreport
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


def test_bug_report_names_the_issue_tracker_of_the_project_urls() -> None:
    assert korml.cli.bugreport.issues_url() == "https://gitlab.com/ambhora/software/korml/-/issues"


def test_lex_drops_a_byte_order_mark(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "a.korml"
    source.write_bytes(b"\xef\xbb\xbfa: 1\n")
    output = tmp_path / "tokens.txt"

    status = _run(monkeypatch, "lex", "--input", str(source), "--output", str(output))

    assert status == 0
    assert "\ufeff" not in output.read_text(encoding="utf-8")


def test_lex_can_atomically_replace_its_own_input(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "source.korml"
    path.write_text("key: value\n", encoding="utf-8")

    assert _run(monkeypatch, "lex", "--input", str(path), "--output", str(path)) == 0
    assert '"value": "key"' in path.read_text(encoding="utf-8")


def test_lex_replaces_output_symlink_not_its_target(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.korml"
    source.write_text("key: value\n", encoding="utf-8")
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched", encoding="utf-8")
    output = tmp_path / "tokens.json"
    output.symlink_to(victim)

    assert _run(monkeypatch, "lex", "--input", str(source), "--output", str(output)) == 0
    assert victim.read_text(encoding="utf-8") == "untouched"
    assert not output.is_symlink()
    assert '"value": "key"' in output.read_text(encoding="utf-8")


def test_lex_failure_does_not_modify_existing_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.korml"
    source.write_bytes(b"\xff")
    output = tmp_path / "tokens.json"
    output.write_bytes(b"original")

    assert _run(monkeypatch, "lex", "--input", str(source), "--output", str(output)) == 1
    assert output.read_bytes() == b"original"


def test_cli_rejects_large_input_without_modifying_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import korml._limits

    monkeypatch.setattr(korml._limits, "MAX_INPUT_BYTES", 10)
    source = tmp_path / "large.korml"
    source.write_bytes(b"x" * 50)
    output = tmp_path / "output.json"
    output.write_bytes(b"unchanged")

    assert _run(monkeypatch, "lex", "--input", str(source), "--output", str(output)) == 1
    assert output.read_bytes() == b"unchanged"
