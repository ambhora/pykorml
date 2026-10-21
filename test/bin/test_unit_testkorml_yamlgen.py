# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import json
import pathlib

import pytest
import testkorml.yamlgen

import korml
import korml.lexer.v1
import korml.lexer.v1.file


def test_generate_single_case_returns_passing_generated_case() -> None:
    case = testkorml.yamlgen.generate_single_case(testkorml.yamlgen.GenerationConfig(seed=1))

    assert case.name == "generated"
    assert case.should_fail is False
    assert case.source.startswith("%!korml version 1.0\n---\n")

    korml.lexer.v1.file.lex("<test>", case.source)


def test_generate_case_set_returns_requested_number_of_pass_cases() -> None:
    case_array = testkorml.yamlgen.generate_case_set(
        testkorml.yamlgen.GenerationConfig(seed=1),
        case_count=5,
        failure_count=0,
    )

    assert len(case_array) == 5
    assert all(not case.should_fail for case in case_array)


def test_generate_case_set_returns_requested_fail_cases() -> None:
    case_array = testkorml.yamlgen.generate_case_set(
        testkorml.yamlgen.GenerationConfig(seed=1),
        case_count=5,
        failure_count=3,
    )

    fail_case_array = [case for case in case_array if case.should_fail]

    assert len(fail_case_array) == 3

    for case in fail_case_array:
        with pytest.raises(korml.LexError):
            korml.lexer.v1.file.lex("<test>", case.source)


def test_generate_case_set_rejects_non_positive_case_count() -> None:
    with pytest.raises(ValueError, match="case_count"):
        testkorml.yamlgen.generate_case_set(
            testkorml.yamlgen.GenerationConfig(seed=1),
            case_count=0,
        )


def test_generate_case_set_rejects_negative_failure_count() -> None:
    with pytest.raises(ValueError, match="failure_count"):
        testkorml.yamlgen.generate_case_set(
            testkorml.yamlgen.GenerationConfig(seed=1),
            case_count=1,
            failure_count=-1,
        )


def test_expected_token_array_matches_lexer_output() -> None:
    source = "%!korml version 1.0\n---\nkey: value\n"

    expected = testkorml.yamlgen.expected_token_array(source)
    token_file = korml.lexer.v1.file.lex("<test>", source)

    assert expected == [token.to_dict() for token in token_file.token_array]


def test_write_pass_case_writes_input_and_expected_json(tmp_path: pathlib.Path) -> None:
    source = "%!korml version 1.0\n---\nkey: value\n"

    testkorml.yamlgen.write_pass_case(
        source=source,
        output=tmp_path,
    )

    assert (tmp_path / "input.korml").read_text(encoding="utf-8") == source

    expected = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))

    assert expected == testkorml.yamlgen.expected_token_array(source)


def test_write_fail_case_writes_input_and_error_json(tmp_path: pathlib.Path) -> None:
    source = ""

    testkorml.yamlgen.write_fail_case(
        source=source,
        output=tmp_path,
        name="empty_source_missing_version_directive",
    )

    assert (tmp_path / "input.korml").read_text(encoding="utf-8") == source

    error = json.loads((tmp_path / "unexpected.error.json").read_text(encoding="utf-8"))

    assert "code" in error
    assert isinstance(error["code"], str)


def test_write_fail_case_rejects_source_that_passes_lexing(tmp_path: pathlib.Path) -> None:
    source = "%!korml version 1.0\n---\nkey: value\n"

    with pytest.raises(RuntimeError, match="expected mutated"):
        testkorml.yamlgen.write_fail_case(
            source=source,
            output=tmp_path,
            name="not_actually_failing",
        )
