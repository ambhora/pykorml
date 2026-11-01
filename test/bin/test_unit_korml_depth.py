# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""The max_depth keyword of every entry point that walks a document."""

import pathlib

import pytest

import korml
import korml.emitter.v0
import korml.emitter.v1
import korml.lexer.file
import korml.parser.v0
import korml.parser.v1

_TREE_SCHEMA = {
    "schema": "korml.schema.v1",
    "root": {"type": "List"},
    "types": {"List": {"kind": "sequence", "items": {"type": "List"}}},
}


def _flow(levels: int) -> str:
    return "[" * levels + "]" * levels + "\n"


def _block(levels: int) -> str:
    return "- " * (levels - 1) + "[]\n"


def _lists(levels: int) -> list[object]:
    value: list[object] = []
    for _ in range(levels - 1):
        value = [value]
    return value


def _assert_too_deep(error: korml.KormlError) -> None:
    assert error.code() == "TOO_DEEP"
    assert isinstance(error, korml.KormlError)


@pytest.mark.parametrize("source", [_flow, _block])
def test_loads_accepts_128_levels_and_rejects_129_by_default(source: object) -> None:
    assert korml.loads(source(128)).to_builtin() == [_lists(128)]

    with pytest.raises(korml.ParseError) as error_info:
        korml.loads(source(129))

    _assert_too_deep(error_info.value)


@pytest.mark.parametrize("source", [_flow, _block])
def test_loads_lower_and_higher_max_depth(source: object) -> None:
    assert korml.loads(source(5), max_depth=5).to_builtin() == [_lists(5)]

    with pytest.raises(korml.ParseError, match="deeper than 4 levels"):
        korml.loads(source(5), max_depth=4)

    stream = korml.loads(source(200), max_depth=200)

    assert stream.to_builtin(max_depth=200) == [_lists(200)]


@pytest.mark.parametrize("source", [_flow, _block])
def test_loads_without_limit_reports_python_recursion_as_too_deep(source: object) -> None:
    with pytest.raises(korml.ParseError) as error_info:
        korml.loads(source(20_000), max_depth=None, max_tokens=None, max_parse_work=None)

    _assert_too_deep(error_info.value)


def test_load_and_parsers_take_max_depth(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "deep.korml"
    path.write_text(_flow(10), encoding="utf-8")

    assert korml.load(path, max_depth=10).to_builtin() == [_lists(10)]

    with pytest.raises(korml.ParseError):
        korml.load(path, max_depth=9)

    v0_file = korml.lexer.file.lex("<test>", _flow(10))
    v1_file = korml.lexer.file.lex("<test>", "%!korml version 1.0\n---\n" + _flow(10) + "...\n")

    for parse, file in ((korml.parser.v0.parse, v0_file), (korml.parser.v1.parse, v1_file)):
        assert parse(file, max_depth=10).to_builtin(max_depth=10) == [_lists(10)]

        with pytest.raises(korml.ParseError):
            parse(file, max_depth=9)


def test_dumps_and_dump_take_max_depth(tmp_path: pathlib.Path) -> None:
    assert korml.loads(korml.dumps(_lists(128))).to_builtin() == [_lists(128)]

    with pytest.raises(korml.error.EmitError) as error_info:
        korml.dumps(_lists(129))

    _assert_too_deep(error_info.value)

    with pytest.raises(korml.error.EmitError, match="deeper than 3 levels"):
        korml.dumps(_lists(4), max_depth=3)

    assert korml.loads(korml.dumps(_lists(200), max_depth=200), max_depth=200).to_builtin(
        max_depth=200
    ) == [_lists(200)]

    with pytest.raises(korml.error.EmitError) as error_info:
        korml.dumps(_lists(20_000), max_depth=None)

    _assert_too_deep(error_info.value)

    path = tmp_path / "out.korml"

    with pytest.raises(korml.error.EmitError):
        korml.dump(_lists(5), path, max_depth=4)

    assert not path.exists()
    korml.dump(_lists(5), path, max_depth=5)
    assert korml.load(path).to_builtin() == [_lists(5)]


def test_emitters_take_max_depth() -> None:
    stream = korml.loads(_flow(6))
    v1_stream = korml.loads(korml.dumps(stream.to_builtin()[0]))

    assert korml.emitter.v0.emit(stream, max_depth=6)

    with pytest.raises(korml.error.EmitError):
        korml.emitter.v0.emit(stream, max_depth=5)

    with pytest.raises(korml.error.EmitError):
        korml.emitter.v1.emit(v1_stream, max_depth=5)


def test_to_builtin_takes_max_depth() -> None:
    stream = korml.loads(_flow(10))

    with pytest.raises(korml.KormlError) as error_info:
        stream.to_builtin(max_depth=9)

    _assert_too_deep(error_info.value)

    with pytest.raises(korml.KormlError):
        stream[0].to_builtin(max_depth=9)

    assert stream[0].to_builtin(max_depth=None) == _lists(10)


def test_edit_takes_max_depth() -> None:
    stream = korml.loads(_block(150), max_depth=150)
    value = stream[0]

    for _ in range(149):
        value = value[0]

    with pytest.raises(korml.KormlError):
        korml.edit(stream=stream, replacements=[(value, "x")])

    edited = korml.edit(stream=stream, replacements=[(value, "x")], max_depth=150)

    assert korml.loads(edited, max_depth=150).to_builtin(max_depth=150)


@pytest.mark.parametrize("function", [korml.schema.validate, korml.schema.construct])
def test_schema_functions_take_max_depth(function: object) -> None:
    schema = korml.schema.compile_schema(_TREE_SCHEMA)

    assert korml.schema.validate(_lists(128), schema) == []

    with pytest.raises(korml.schema.InvalidValueError) as error_info:
        function(_lists(129), schema)

    _assert_too_deep(error_info.value)

    with pytest.raises(korml.schema.InvalidValueError):
        function(_lists(5), schema, max_depth=4)

    function(_lists(200), schema, max_depth=200)

    with pytest.raises(korml.schema.InvalidValueError) as error_info:
        function(_lists(20_000), schema, max_depth=None)

    _assert_too_deep(error_info.value)


def test_model_assignment_is_unguarded_but_walks_honour_max_depth() -> None:
    mapping = korml.Mapping(cst=korml.CST(version=korml.Version.v1))
    mapping["deep"] = _lists(300)

    with pytest.raises(korml.error.EmitError):
        korml.dumps(mapping)

    with pytest.raises(korml.KormlError):
        mapping.to_builtin()

    builtin = mapping.to_builtin(max_depth=301)
    schema = korml.schema.compile_schema(
        {
            **_TREE_SCHEMA,
            "root": {"type": "Map"},
            "types": {
                **_TREE_SCHEMA["types"],
                "Map": {"kind": "mapping", "values": {"type": "List"}},
            },
        }
    )

    with pytest.raises(korml.schema.InvalidValueError):
        korml.schema.validate(builtin, schema)

    assert korml.schema.validate(builtin, schema, max_depth=301) == []
    assert korml.loads(korml.dumps(mapping, max_depth=301), max_depth=301)


@pytest.mark.parametrize("max_depth", [0, -1])
def test_non_positive_max_depth_is_a_value_error(max_depth: int) -> None:
    calls = [
        lambda: korml.loads("a\n", max_depth=max_depth),
        lambda: korml.dumps("a", max_depth=max_depth),
        lambda: korml.loads("a\n").to_builtin(max_depth=max_depth),
        lambda: korml.schema.validate(
            [], korml.schema.compile_schema(_TREE_SCHEMA), max_depth=max_depth
        ),
        lambda: korml.edit(stream=korml.loads("a\n"), replacements=[], max_depth=max_depth),
    ]

    for call in calls:
        with pytest.raises(ValueError, match="max_depth"):
            call()


@pytest.mark.parametrize("max_depth", ["3", 2.5, True])
def test_non_integer_max_depth_is_a_type_error(max_depth: object) -> None:
    with pytest.raises(TypeError, match="max_depth"):
        korml.loads("a\n", max_depth=max_depth)
