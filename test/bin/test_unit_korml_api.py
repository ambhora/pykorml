# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import pathlib

import pytest

import korml


def test_loads_parses_single_document_mapping() -> None:
    stream = korml.loads("%!korml version 1.0\n---\na: b\n...\n")

    assert stream.to_builtin() == [{"a": "b"}]


def test_dumps_emits_parseable_stream() -> None:
    source = korml.dumps({"a": ["b", {"c": "d"}]})

    assert source.startswith("%!korml version 1.0\n---\n")
    assert korml.loads(source).to_builtin() == [{"a": ["b", {"c": "d"}]}]


def test_dumps_emits_multiline_string_as_literal_block_scalar() -> None:
    source = korml.dumps({"message": "hello\nworld\n"})

    assert '"message": |\n' in source
    assert korml.loads(source).to_builtin() == [{"message": "hello\nworld\n"}]


def test_dumps_accepts_korml_value_as_single_document() -> None:
    value = korml.Scalar("hello", cst=korml.CST(version=korml.Version.v1))

    assert korml.loads(korml.dumps(value)).to_builtin() == ["hello"]


def test_dump_writes_file_and_load_reads_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "document.korml"

    korml.dump({"x": "y"}, path)

    assert korml.load(path).to_builtin() == [{"x": "y"}]


def test_dumps_rejects_non_string_mapping_key() -> None:
    with pytest.raises(TypeError, match="mapping keys"):
        korml.dumps({1: "x"})
