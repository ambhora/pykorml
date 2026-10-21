# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import json
import pathlib

import pytest

import korml.lexer.v1.file

CASE_ROOT = pathlib.Path("test/share/functional/lexer/v1")


def case_dirs() -> list[pathlib.Path]:
    return sorted(path for path in CASE_ROOT.iterdir() if path.is_dir())


@pytest.mark.parametrize("case_dir", case_dirs(), ids=lambda path: path.name)
def test_functional_lex(case_dir: pathlib.Path) -> None:
    input_path = case_dir / "input.korml"

    input_text = input_path.read_bytes().decode("utf-8")

    if str(case_dir).endswith(".fail"):
        expected_path = case_dir / "unexpected.error.json"

        with expected_path.open("r", encoding="utf-8") as f:
            expected = json.load(f)

        expected_code = korml.lexer.v1.ErrorCode(expected["code"])

        with pytest.raises(korml.error.LexError) as exc_info:
            korml.lexer.v1.file.lex(input_path, input_text)

        exception = exc_info.value

        assert exception.code() == expected_code

    else:
        expected_path = case_dir / "expected.json"
        expected_token_array = json.loads(expected_path.read_text(encoding="utf-8"))

        token_file = korml.lexer.v1.file.lex(input_path, input_text)
        actual_token_array = [token.to_dict() for token in token_file.token_array]

        assert actual_token_array == expected_token_array


@pytest.mark.parametrize(
    "case_dir",
    [path for path in case_dirs() if (path / "expected.json").exists()],
    ids=lambda path: path.name,
)
def test_functional_unlex_roundtrip(case_dir: pathlib.Path) -> None:
    input_path = case_dir / "input.korml"
    input_text = input_path.read_text(encoding="utf-8")

    token_array = korml.lexer.v1.file.lex("default", input_text)
    output_text = korml.lexer.v1.file.unlex(token_array)

    assert output_text == input_text
