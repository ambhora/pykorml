# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Empty documents: kept in the stream as korml.Empty, None in plain data."""

import pytest

import korml
import korml.emitter.v0
import korml.emitter.v1
import korml.lexer.file

_DIRECTIVE = "%!korml version 1.0\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("---\n...\n---\na: 1\n...\n", [None, {"a": "1"}]),
        ("---\na: 1\n...\n---\n...\n---\nb: 2\n...\n", [{"a": "1"}, None, {"b": "2"}]),
        ("---\na: 1\n...\n---\n...\n", [{"a": "1"}, None]),
        ("---\n...\n---\n...\n---\n...\n", [None, None, None]),
        ("---\n# only a comment\n\n   \n...\n", [None]),
        ("---\n...", [None]),
    ],
    ids=["first", "middle", "last", "consecutive", "comment-only", "no-final-break"],
)
def test_v1_empty_documents_are_kept(source: str, expected: list[object]) -> None:
    text = _DIRECTIVE + source
    stream = korml.loads(text)

    assert stream.to_builtin() == expected
    assert [isinstance(document, korml.Empty) for document in stream] == [
        value is None for value in expected
    ]
    assert korml.lexer.file.unlex(korml.lexer.file.lex("<test>", text)) == text


@pytest.mark.parametrize("source", ["", "\n", "# comment\n", "  \n# a\n\n# b"])
def test_v0_empty_or_blank_source_is_one_empty_document(source: str) -> None:
    stream = korml.loads(source)

    assert len(stream) == 1
    assert isinstance(stream[0], korml.Empty)
    assert stream.to_builtin() == [None]
    assert stream[0].source == source


def test_empty_document_keeps_the_comments_between_its_markers() -> None:
    stream = korml.loads(_DIRECTIVE + "---\n# keep me\n...\n")

    assert "# keep me" in stream[0].source


def test_empty_documents_round_trip_through_dumps() -> None:
    source = _DIRECTIVE + "---\n...\n---\na: 1\n...\n---\n...\n"

    text = korml.dumps(korml.loads(source))

    assert text == _DIRECTIVE + '---\n...\n---\n"a": "1"\n...\n---\n...\n'
    assert korml.loads(text).to_builtin() == [None, {"a": "1"}, None]


def test_empty_document_emitters() -> None:
    v1_stream = korml.Stream(
        document_array=[korml.Empty(cst=korml.CST(version=korml.Version.v1))],
        cst=korml.CST(version=korml.Version.v1),
    )
    v0_stream = korml.Stream(
        document_array=[korml.Empty(cst=korml.CST(version=korml.Version.v0))],
        cst=korml.CST(version=korml.Version.v0),
    )

    assert korml.emitter.v1.emit(v1_stream) == _DIRECTIVE + "---\n...\n"
    assert korml.emitter.v0.emit(v0_stream) == ""
    assert korml.loads(korml.emitter.v0.emit(v0_stream)).to_builtin() == [None]


@pytest.mark.parametrize("version", [korml.Version.v0, korml.Version.v1])
def test_none_at_the_top_dumps_as_an_empty_document(version: korml.Version) -> None:
    assert korml.loads(korml.dumps(None, version=version)).to_builtin() == [None]


@pytest.mark.parametrize("value", [[None], {"a": None}])
def test_none_inside_a_collection_cannot_be_dumped(value: object) -> None:
    with pytest.raises(TypeError):
        korml.dumps(value)


def test_empty_is_refused_inside_collections() -> None:
    cst = korml.CST(version=korml.Version.v1)
    empty = korml.Empty(cst=cst)

    with pytest.raises(TypeError, match="root of a document"):
        korml.Sequence(value_array=[empty], cst=cst)

    with pytest.raises(TypeError, match="root of a document"):
        korml.Mapping(value_map={"a": empty}, cst=cst)

    with pytest.raises(TypeError, match="root of a document"):
        korml.Sequence(cst=cst).append(empty)

    with pytest.raises(TypeError, match="root of a document"):
        korml.Mapping(cst=cst).add_item("a", empty)

    with pytest.raises(TypeError):
        korml.Mapping(cst=cst)["a"] = empty


def test_emitter_refuses_an_empty_smuggled_into_a_collection() -> None:
    cst = korml.CST(version=korml.Version.v1)
    sequence = korml.Sequence(cst=cst)
    sequence.value_array.append(korml.Empty(cst=cst))

    with pytest.raises(korml.error.EmitError, match="root of a document"):
        korml.dumps(sequence)


def test_empty_repr_and_equality() -> None:
    empty = korml.Empty(cst=korml.CST(version=korml.Version.v1))

    assert repr(empty).startswith("Empty(")
    assert empty == korml.Empty()
    assert empty != korml.Scalar("")
    assert empty.to_builtin() is None
    assert korml.loads("").to_builtin() == korml.loads(_DIRECTIVE + "---\n...\n").to_builtin()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_DIRECTIVE + "---\n...\n", _DIRECTIVE + '---\n"x"\n...\n'),
        (_DIRECTIVE + "---\n# c\n...\n", _DIRECTIVE + '---\n"x"\n# c\n...\n'),
        (
            "%!korml version 1.0\r\n---\r\n...\r\n",
            '%!korml version 1.0\r\n---\r\n"x"\r\n...\r\n',
        ),
        ("", '"x"\n'),
        ("# c\n", '"x"\n# c\n'),
    ],
)
def test_edit_gives_an_empty_document_a_root_scalar(source: str, expected: str) -> None:
    stream = korml.loads(source)

    assert korml.edit(stream=stream, replacements=[(stream[0], "x")]) == expected


@pytest.mark.parametrize("source", ["", _DIRECTIVE + "---\n...\n"])
def test_edit_refuses_to_replace_an_empty_document_twice(source: str) -> None:
    stream = korml.loads(source)

    with pytest.raises(ValueError, match="overlap"):
        korml.edit(stream=stream, replacements=[(stream[0], "x"), (stream[0], "y")])


def test_edit_keeps_empty_documents_it_does_not_replace() -> None:
    source = _DIRECTIVE + "---\n...\n---\na: 1\n...\n"
    stream = korml.loads(source)

    edited = korml.edit(stream=stream, replacements=[(stream[1]["a"], "2")])

    assert korml.loads(edited).to_builtin() == [None, {"a": "2"}]


_SCHEMA = {
    "schema": "korml.schema.v1",
    "root": {"type": "Config"},
    "types": {
        "Config": {"kind": "mapping", "values": {"type": "Anything"}},
        "Anything": {"kind": "any"},
    },
}


def test_schema_reports_an_empty_document_unless_the_root_is_any() -> None:
    schema = korml.schema.compile_schema(_SCHEMA)
    any_schema = korml.schema.compile_schema({**_SCHEMA, "root": {"type": "Anything"}})
    document = korml.loads("").to_builtin()[0]

    error_array = korml.schema.validate(document, schema)

    assert [error.code for error in error_array] == [korml.schema.ErrorCode.EMPTY_DOCUMENT]
    assert korml.schema.validate(korml.loads("")[0], schema) == error_array
    assert korml.schema.validate(document, any_schema) == []

    with pytest.raises(korml.schema.ConstructionError, match="document is empty"):
        korml.schema.construct(document, schema, {"Config": dict})


def test_schema_constructs_an_empty_document_as_none_without_constructors() -> None:
    any_schema = korml.schema.compile_schema({**_SCHEMA, "root": {"type": "Anything"}})

    def fail(value: object) -> object:
        raise AssertionError("no constructor runs for an empty document")

    assert korml.schema.construct(None, any_schema, {"Anything": fail}) is None
