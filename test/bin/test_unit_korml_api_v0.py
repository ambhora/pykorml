# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import pathlib

import korml


def test_loads_detects_v0_for_unframed_single_document() -> None:
    stream = korml.loads("a: b\n")

    assert stream.version is korml.Version.v0
    assert stream.to_builtin() == [{"a": "b"}]


def test_dumps_can_emit_v0() -> None:
    source = korml.dumps({"a": ["b", {"c": "d"}]}, version=korml.Version.v0)

    assert not source.startswith("%!korml")
    assert "---" not in source
    assert "..." not in source
    assert korml.loads(source).to_builtin() == [{"a": ["b", {"c": "d"}]}]


def test_dump_writes_v0_file_and_load_reads_v0_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "document.korml"

    korml.dump({"x": "y"}, path, version=korml.Version.v0)

    assert path.read_text(encoding="utf-8") == '"x": "y"\n'
    assert korml.load(path).to_builtin() == [{"x": "y"}]
