# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Regression tests for the findings of the security review."""

import dataclasses
import io
import os
import pathlib
import sys

import pytest

import korml
import korml.cli.bugreport
import korml.error

# --------------------------------------------------------------------------------------------------
# Schema construction: document keys must not reach constructor parameters
# --------------------------------------------------------------------------------------------------

_JOB_SCHEMA = {
    "schema": "korml.schema.v1",
    "root": {"type": "Job"},
    "types": {
        "String": {"kind": "scalar"},
        "Job": {
            "kind": "mapping",
            "required": ["cmd"],
            "fields": {"cmd": {"type": "String"}},
            "values": {"type": "String"},
        },
        "Labels": {"kind": "mapping", "values": {"type": "String"}},
        "Point": {
            "kind": "mapping",
            "fields": {"x": {"type": "String"}, "y": {"type": "String"}},
        },
    },
}


@dataclasses.dataclass
class _Job:
    labels: dict[str, str]
    cmd: str
    sandbox: str = "true"


def test_open_ended_entries_cannot_override_constructor_parameters() -> None:
    # Before the fix, 'sandbox' was passed as a keyword argument and turned
    # the sandbox of the constructed job off.
    document = korml.loads('cmd: "rm -rf /"\nsandbox: "false"\n').to_builtin()[0]
    schema = korml.schema.compile_schema(_JOB_SCHEMA)

    job = korml.schema.construct(document, schema, {"Job": _Job})

    assert job == _Job(labels={"sandbox": "false"}, cmd="rm -rf /", sandbox="true")


def test_mapping_with_only_values_gets_its_entries_as_one_argument() -> None:
    schema = korml.schema.compile_schema({**_JOB_SCHEMA, "root": {"type": "Labels"}})

    labels = korml.schema.construct({"a": "1", "self": "2"}, schema, {"Labels": dict})

    assert labels == {"a": "1", "self": "2"}


def test_mapping_without_values_gets_its_fields_as_keywords() -> None:
    schema = korml.schema.compile_schema({**_JOB_SCHEMA, "root": {"type": "Point"}})

    point = korml.schema.construct({"x": "1", "y": "2"}, schema, {"Point": lambda **kw: kw})

    assert point == {"x": "1", "y": "2"}


# --------------------------------------------------------------------------------------------------
# Raw invisible, control and surrogate characters
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    ["admin​: true\n", "'admin​': true\n", "admin⁠: true\n", "admin‍: true\n"],
)
def test_keys_cannot_be_spoofed_with_invisible_characters(source: str) -> None:
    with pytest.raises(korml.KormlError):
        korml.loads(f"admin: false\n{source}")


@pytest.mark.parametrize("source", ["a: 'x‮y'\n", "# ⁦comment\na: 1\n"])
def test_bidirectional_controls_are_refused_even_in_quotes_and_comments(source: str) -> None:
    with pytest.raises(korml.LexError, match="not allowed"):
        korml.loads(source)


def test_lone_surrogate_in_loads_is_a_lex_error() -> None:
    with pytest.raises(korml.LexError, match="U\\+DCFF"):
        korml.loads("a: \udcff\n")


@pytest.mark.parametrize("version", [korml.Version.v0, korml.Version.v1])
def test_lone_surrogate_in_dumps_is_a_korml_error(version: korml.Version) -> None:
    with pytest.raises(korml.error.EmitError, match="lone surrogate") as error_info:
        korml.dumps({"a": "\udcff"}, version=version)

    assert isinstance(error_info.value, korml.KormlError)

    with pytest.raises(korml.error.EmitError):
        korml.dumps({"\ud800": "a"}, version=version)


def test_lone_surrogate_in_dump_is_a_korml_error_and_writes_nothing(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "out.korml"

    with pytest.raises(korml.KormlError):
        korml.dump(["\ud800"], path)

    assert not path.exists()


def test_controls_are_emitted_as_unicode_escapes() -> None:
    text = korml.dumps({"\x1b": "\x1b\x00\x07\x0b\x7f\x85 ​‌"})

    assert "\\u001b" in text
    assert "\\e" not in text and "\\x" not in text and "\\0" not in text
    assert all(char == "\n" or char.isprintable() for char in text)
    assert korml.loads(text).to_builtin() == [{"\x1b": "\x1b\x00\x07\x0b\x7f\x85 ​‌"}]


def test_key_longer_than_a_source_may_hold_is_an_emit_error() -> None:
    assert korml.loads(korml.dumps({"k" * 1022: "v"})).to_builtin() == [{"k" * 1022: "v"}]

    with pytest.raises(korml.error.EmitError, match="1024"):
        korml.dumps({"k" * 1023: "v"})


# --------------------------------------------------------------------------------------------------
# Recursion over plain Python values
# --------------------------------------------------------------------------------------------------


def _nested_list(depth: int) -> list[object]:
    value: list[object] = []
    for _ in range(depth):
        value = [value]
    return value


def _cyclic_dict() -> dict[str, object]:
    value: dict[str, object] = {}
    value["self"] = value
    return value


def test_dumps_refuses_deep_nesting_with_a_korml_error() -> None:
    assert korml.loads(korml.dumps(_nested_list(128))).to_builtin() == [_nested_list(128)]

    with pytest.raises(korml.error.EmitError, match="nested deeper"):
        korml.dumps(_nested_list(129))

    with pytest.raises(korml.error.EmitError, match="nested deeper"):
        korml.dumps(_nested_list(5000))


@pytest.mark.parametrize("value", [_cyclic_dict(), [[]]])
def test_dumps_refuses_cycles_with_a_korml_error(value: object) -> None:
    if isinstance(value, list):
        value[0].append(value)

    with pytest.raises(korml.error.EmitError, match="contains itself"):
        korml.dumps(value)


def test_dumps_writes_a_shared_container_twice() -> None:
    shared = ["x"]

    assert korml.loads(korml.dumps([shared, shared])).to_builtin() == [[["x"], ["x"]]]


_TREE_SCHEMA = {
    "schema": "korml.schema.v1",
    "root": {"type": "Tree"},
    "types": {
        "Tree": {"kind": "mapping", "values": {"type": "Tree"}},
        "List": {"kind": "sequence", "items": {"type": "List"}},
    },
}


def _nested_dict(depth: int) -> dict[str, object]:
    value: dict[str, object] = {}
    for _ in range(depth):
        value = {"child": value}
    return value


@pytest.mark.parametrize("function", [korml.schema.validate, korml.schema.construct])
def test_schema_refuses_deep_nesting_with_a_korml_error(function: object) -> None:
    schema = korml.schema.compile_schema(_TREE_SCHEMA)

    assert korml.schema.validate(_nested_dict(128), schema) == []

    with pytest.raises(korml.schema.v1.InvalidValueError, match="nested deeper") as error_info:
        function(_nested_dict(5000), schema)

    assert isinstance(error_info.value, korml.KormlError)
    assert error_info.value.code() == "TOO_DEEP"


@pytest.mark.parametrize("function", [korml.schema.validate, korml.schema.construct])
def test_schema_refuses_cycles_with_a_korml_error(function: object) -> None:
    schema = korml.schema.compile_schema(_TREE_SCHEMA)
    list_schema = korml.schema.compile_schema({**_TREE_SCHEMA, "root": {"type": "List"}})
    cyclic_list: list[object] = []
    cyclic_list.append(cyclic_list)

    with pytest.raises(korml.schema.v1.InvalidValueError, match="contains itself") as error_info:
        function(_cyclic_dict(), schema)

    assert error_info.value.code() == "CYCLIC_VALUE"

    with pytest.raises(korml.schema.v1.InvalidValueError, match="contains itself"):
        function(cyclic_list, list_schema)


def test_schema_accepts_a_shared_container() -> None:
    schema = korml.schema.compile_schema(_TREE_SCHEMA)
    shared: dict[str, object] = {}

    assert korml.schema.validate({"a": shared, "b": shared}, schema) == []


# --------------------------------------------------------------------------------------------------
# Bug report and file input
# --------------------------------------------------------------------------------------------------


def test_bug_report_escapes_the_exception_message() -> None:
    try:
        raise RuntimeError("bad\x1b[2Jinput\nsecond line")
    except RuntimeError as error:
        report = korml.cli.bugreport.render_internal_failure_report(error, io.StringIO())

    assert "\x1b[2J" not in report
    assert "- Exception message: bad\\x1b[2Jinput\nsecond line" in report


@pytest.mark.skipif(sys.platform == "win32", reason="FIFOs are a POSIX feature")
def test_load_refuses_a_fifo(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "fifo"
    os.mkfifo(path)

    with pytest.raises(korml.error.CompilerError, match="not a regular file") as error_info:
        korml.load(path)

    assert error_info.value.code() == "NOT_A_REGULAR_FILE"


def test_load_refuses_a_directory(tmp_path: pathlib.Path) -> None:
    with pytest.raises(korml.error.CompilerError, match="not a regular file"):
        korml.load(tmp_path)


def test_load_reads_a_regular_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "a.korml"
    path.write_text("a: 1\n", encoding="utf-8")

    assert korml.load(path).to_builtin() == [{"a": "1"}]
