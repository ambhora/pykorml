# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""How the emitters limit the length of their output."""

import inspect
import pathlib
import tracemalloc

import pytest

import korml

_V0 = korml.model.Version.v0

_SMALL_LIMIT = 8 * 1024 * 1024

_VALUES = [
    None,
    "a scalar at the root",
    {},
    [],
    {"a": "x", "b": ["y", "z"], "c": {}},
    {"kéy": "välue \U0001f600", "quoted": 'a "b"\tc', "empty": []},
    {"block": "line one\nline two\nline three\n", "list": ["first\nsecond\n", {}]},
    [[[["deep", {"deeper": "x\ny\n"}]]]],
    {"über": {"block": "ä\nö\n"}, "e": [[], {}]},
]


def _nested(depth: int, leaf: object) -> object:
    """
    Return leaf inside depth single-key mappings.

    @param depth The number of mappings around leaf.

    @param leaf The innermost value.

    @return The nested value.
    """
    value = leaf
    for _ in range(depth):
        value = {"a": value}
    return value


@pytest.mark.parametrize("version", [korml.model.Version.v1, _V0])
@pytest.mark.parametrize("value", _VALUES)
def test_the_limit_is_the_exact_length_of_the_output(
    value: object, version: korml.model.Version
) -> None:
    text = korml.dumps(value, version=version)
    size = len(text.encode("utf-8"))

    assert korml.dumps(value, version=version, max_output_bytes=size) == text

    if size == 0:
        return

    with pytest.raises(korml.error.EmitError) as exc_info:
        korml.dumps(value, version=version, max_output_bytes=size - 1)

    assert exc_info.value.code() == "OUTPUT_TOO_LARGE"


@pytest.mark.parametrize("version", [korml.model.Version.v1, _V0])
def test_deeply_indented_block_scalar_is_refused_before_it_is_built(
    version: korml.model.Version,
) -> None:
    # About 100 KB of value whose lines would each carry 242 spaces of
    # indentation: about 12 MB of output.
    value = _nested(120, "a\n" * 50_000)

    tracemalloc.start()
    try:
        with pytest.raises(korml.error.EmitError) as exc_info:
            korml.dumps(value, version=version, max_output_bytes=_SMALL_LIMIT)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert exc_info.value.code() == "OUTPUT_TOO_LARGE"
    assert str(_SMALL_LIMIT) in exc_info.value.message()
    assert peak < 4 * 1024 * 1024


def test_many_indented_lines_are_refused_while_they_are_built() -> None:
    # Many small entries deep down, each line well inside the limit.
    value = _nested(100, {f"k{index}": "v" for index in range(60_000)})

    with pytest.raises(korml.error.EmitError) as exc_info:
        korml.dumps(value, max_output_bytes=_SMALL_LIMIT)

    assert exc_info.value.code() == "OUTPUT_TOO_LARGE"
    assert len(korml.dumps(value, max_output_bytes=None)) > _SMALL_LIMIT


@pytest.mark.parametrize(
    "function", [korml.dumps, korml.dump, korml.emitter.v1.emit, korml.emitter.v0.emit]
)
def test_default_limit_is_4_gib(function: object) -> None:
    default = inspect.signature(function).parameters["max_output_bytes"].default  # type: ignore[arg-type]

    assert default == korml._limits.MAX_OUTPUT_BYTES == 4 * 1024 * 1024 * 1024


def test_dump_writes_nothing_when_the_output_is_too_long(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "out.korml"
    path.write_text("old\n", encoding="utf-8")

    with pytest.raises(korml.error.EmitError):
        korml.dump({"a": "x" * 100}, path, max_output_bytes=50)

    assert path.read_text(encoding="utf-8") == "old\n"
    assert list(tmp_path.iterdir()) == [path]

    korml.dump({"a": "x" * 100}, path, max_output_bytes=None)

    assert korml.load(path).to_builtin() == [{"a": "x" * 100}]


def test_emitters_take_max_output_bytes() -> None:
    v1_stream = korml.loads(korml.dumps({"a": "x"}))
    v0_stream = korml.loads('a: "x"\n')

    assert korml.emitter.v1.emit(v1_stream, max_output_bytes=None)
    assert korml.emitter.v0.emit(v0_stream, max_output_bytes=None)

    for emit, stream in ((korml.emitter.v1.emit, v1_stream), (korml.emitter.v0.emit, v0_stream)):
        with pytest.raises(korml.error.EmitError):
            emit(stream, max_output_bytes=3)


@pytest.mark.parametrize("max_output_bytes", [-1, -100])
def test_negative_max_output_bytes_is_a_value_error(max_output_bytes: int) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        korml.dumps("x", max_output_bytes=max_output_bytes)


@pytest.mark.parametrize("max_output_bytes", [True, 1.5, "10"])
def test_non_integer_max_output_bytes_is_a_type_error(max_output_bytes: object) -> None:
    with pytest.raises(TypeError, match="max_output_bytes must be an integer or None"):
        korml.dumps("x", max_output_bytes=max_output_bytes)  # type: ignore[arg-type]
