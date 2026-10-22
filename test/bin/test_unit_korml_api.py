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


def test_dump_refuses_to_write_through_a_symlink(tmp_path: pathlib.Path) -> None:
    victim = tmp_path / "victim.korml"
    victim.write_text("secret", encoding="utf-8")
    destination = tmp_path / "output.korml"
    destination.symlink_to(victim)

    with pytest.raises(korml.error.UnsafeOutputError, match="symbolic link"):
        korml.dump({"key": "value"}, destination)

    assert destination.is_symlink()
    assert victim.read_text(encoding="utf-8") == "secret"


def test_dump_writes_the_symlink_target_when_allowed(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "target.korml"
    target.write_text("old", encoding="utf-8")
    link = tmp_path / "link.korml"
    link.symlink_to(target)

    korml.dump({"key": "value"}, link, dangerous_allow_writing_to_symlink=True)

    assert link.is_symlink()
    assert korml.load(target).to_builtin() == [{"key": "value"}]


def test_dump_preserves_existing_mode(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "private.korml"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o600)

    korml.dump({"a": "b"}, path)

    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("source", ["[a, [b, c]]", "a: [b, c]"])
def test_parser_work_limit_rejects_complex_inputs(source: str) -> None:
    with pytest.raises(korml.ParseError) as exc:
        korml.loads(source, max_parse_work=3)
    assert exc.value.code() == "TOO_COMPLEX"


def test_parser_work_limit_can_be_disabled() -> None:
    assert korml.loads("[a, [b, c]]", max_parse_work=None).to_builtin() == [["a", ["b", "c"]]]


def test_token_count_limit_is_structured() -> None:
    with pytest.raises(korml.error.CompilerError) as exc:
        korml.loads("[a, b, c]", max_tokens=2)
    assert exc.value.code() == "TOO_MANY_TOKENS"


def test_input_byte_limit_counts_utf8_bytes() -> None:
    with pytest.raises(korml.error.CompilerError) as exc:
        korml.loads("é", max_input_bytes=1)
    assert exc.value.code() == "INPUT_TOO_LARGE"


def test_load_does_not_read_unbounded_files(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "large.korml"
    path.write_bytes(b"a" * 200)
    with pytest.raises(korml.error.CompilerError) as exc:
        korml.load(path, max_input_bytes=100)
    assert exc.value.code() == "INPUT_TOO_LARGE"


def test_dump_supports_symlinked_parent_directory(tmp_path: pathlib.Path) -> None:
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    symlinked_directory = tmp_path / "link"
    symlinked_directory.symlink_to(real_directory, target_is_directory=True)

    korml.dump({"a": "b"}, symlinked_directory / "output.korml")

    assert korml.load(real_directory / "output.korml").to_builtin() == [{"a": "b"}]


def test_dump_failed_replace_keeps_old_file_and_cleans_temp(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import korml._atomic

    destination = tmp_path / "output.korml"
    destination.write_text("unchanged", encoding="utf-8")

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(korml._atomic.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated rename failure"):
        korml.dump({"a": "b"}, destination)

    assert destination.read_text(encoding="utf-8") == "unchanged"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["output.korml"]


def test_load_of_a_file_that_is_not_utf8_is_a_korml_error(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bad.korml"
    path.write_bytes(b"a: caf\xe9\n")

    with pytest.raises(korml.error.CompilerError, match="not valid UTF-8 at byte 6") as exc_info:
        korml.load(path)

    assert exc_info.value.code() == "INVALID_ENCODING"
