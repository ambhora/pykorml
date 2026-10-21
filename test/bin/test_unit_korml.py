# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc

import pytest

import korml
import korml.core
import korml.lexer.v1


def test_cst_defaults_to_unknown_version_empty_source_and_empty_span() -> None:
    cst = korml.CST[korml.lexer.v1.Token]()

    assert cst.version is korml.Version.unknown
    assert cst.token_array == ()
    assert cst.source == ""
    assert cst.span == korml.core.Span.empty()


def test_cst_source_and_span_come_from_token_array() -> None:
    token_array = korml.lexer.v1.make_token_array(
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "name"),
        (korml.lexer.v1.TokenType.COLON, ":"),
        (korml.lexer.v1.TokenType.WHITESPACE, " "),
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "value"),
        start=korml.core.make_position(
            line=1,
            column=1,
            offset=0,
        ),
    )

    cst = korml.CST[korml.lexer.v1.Token](
        version=korml.Version.v1,
        token_array=token_array,
    )

    assert cst.version is korml.Version.v1
    assert cst.token_array == token_array
    assert cst.source == "name: value"
    assert cst.span == korml.core.Span(
        start=token_array[0].span.start,
        end=token_array[-1].span.end,
    )


def test_value_defaults_to_empty_cst_metadata() -> None:
    value = korml.Value[korml.lexer.v1.Token]()

    assert value.version is korml.Version.unknown
    assert value.token_array == ()
    assert value.source == ""
    assert value.span == korml.core.Span.empty()
    assert value.child_array == ()


def test_value_to_builtin_is_not_implemented() -> None:
    value = korml.Value[korml.lexer.v1.Token]()

    with pytest.raises(NotImplementedError):
        value.to_builtin()


def test_value_style_conversion_is_not_implemented() -> None:
    value = korml.Value[korml.lexer.v1.Token]()

    with pytest.raises(NotImplementedError):
        value.with_style(korml.Style.flow)

    with pytest.raises(NotImplementedError):
        value.to_flow()

    with pytest.raises(NotImplementedError):
        value.to_block()


def test_scalar_stores_string_value() -> None:
    scalar = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(version=korml.Version.v1),
    )

    assert isinstance(scalar, korml.Value)
    assert scalar.version is korml.Version.v1
    assert scalar.value == "hello"
    assert scalar.to_builtin() == "hello"


def test_scalar_equality_ignores_cst() -> None:
    token_array = korml.lexer.v1.make_token_array(
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "hello"),
        start=korml.core.make_position(
            line=1,
            column=1,
            offset=0,
        ),
    )

    parsed = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(
            version=korml.Version.v1,
            token_array=token_array,
        ),
    )
    generated = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(version=korml.Version.unknown),
    )

    assert parsed == generated


def test_scalar_equality_depends_on_scalar_value() -> None:
    first = korml.Scalar[korml.lexer.v1.Token]("first")
    second = korml.Scalar[korml.lexer.v1.Token]("second")

    assert first != second


def test_sequence_defaults_to_empty_sequence() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token]()

    assert isinstance(sequence, korml.Value)
    assert isinstance(sequence, collections.abc.Sequence)
    assert len(sequence) == 0
    assert list(sequence) == []
    assert sequence.to_builtin() == []


def test_sequence_behaves_like_python_sequence_of_korml_values() -> None:
    first = korml.Scalar[korml.lexer.v1.Token](
        "first",
        cst=korml.CST(version=korml.Version.v1),
    )
    second = korml.Scalar[korml.lexer.v1.Token](
        "second",
        cst=korml.CST(version=korml.Version.v1),
    )

    sequence = korml.Sequence[korml.lexer.v1.Token](
        value_array=[first, second],
        cst=korml.CST(version=korml.Version.v1),
    )

    assert len(sequence) == 2
    assert sequence[0] is first
    assert sequence[1] is second
    assert sequence[-1] is second
    assert list(sequence) == [first, second]
    assert sequence.to_builtin() == ["first", "second"]


def test_sequence_raw_assignment_converts_string_to_scalar() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token](
        value_array=[
            korml.Scalar[korml.lexer.v1.Token](
                "old",
                cst=korml.CST(version=korml.Version.v1),
            )
        ],
        cst=korml.CST(version=korml.Version.v1),
    )

    sequence[0] = "new"

    assert isinstance(sequence[0], korml.Scalar)
    assert sequence[0].version is korml.Version.v1
    assert sequence.to_builtin() == ["new"]


def test_sequence_raw_assignment_converts_nested_list_and_dict() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token](
        value_array=[
            korml.Scalar[korml.lexer.v1.Token](
                "old",
                cst=korml.CST(version=korml.Version.v1),
            )
        ],
        cst=korml.CST(version=korml.Version.v1),
    )

    sequence[0] = {"a": ["b", {"c": "d"}]}

    assert sequence.to_builtin() == [
        {
            "a": [
                "b",
                {
                    "c": "d",
                },
            ],
        }
    ]
    assert sequence[0].version is korml.Version.v1


def test_sequence_raw_assignment_rejects_existing_korml_value() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token](
        value_array=[
            korml.Scalar[korml.lexer.v1.Token](
                "old",
                cst=korml.CST(version=korml.Version.v1),
            )
        ],
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        sequence[0] = korml.Scalar[korml.lexer.v1.Token](
            "new",
            cst=korml.CST(version=korml.Version.v1),
        )


def test_sequence_append_accepts_same_version_korml_value() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    value = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(version=korml.Version.v1),
    )

    sequence.append(value)

    assert sequence[0] is value
    assert sequence.to_builtin() == ["hello"]


def test_sequence_append_rejects_raw_value() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        sequence.append("hello")  # type: ignore[arg-type]


def test_sequence_append_rejects_wrong_version_korml_value() -> None:
    sequence = korml.Sequence[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    value = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(version=korml.Version.unknown),
    )

    with pytest.raises(ValueError):
        sequence.append(value)


def test_sequence_constructor_rejects_wrong_version_child() -> None:
    with pytest.raises(ValueError):
        korml.Sequence[korml.lexer.v1.Token](
            value_array=[
                korml.Scalar[korml.lexer.v1.Token](
                    "hello",
                    cst=korml.CST(version=korml.Version.unknown),
                )
            ],
            cst=korml.CST(version=korml.Version.v1),
        )


def test_sequence_style_is_not_part_of_equality() -> None:
    flow = korml.Sequence[korml.lexer.v1.Token](
        style=korml.Style.flow,
    )
    block = korml.Sequence[korml.lexer.v1.Token](
        style=korml.Style.block,
    )

    assert flow == block


def test_mapping_defaults_to_empty_mapping() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token]()

    assert isinstance(mapping, korml.Value)
    assert isinstance(mapping, collections.abc.Mapping)
    assert len(mapping) == 0
    assert list(mapping) == []
    assert dict(mapping) == {}
    assert mapping.to_builtin() == {}


def test_mapping_behaves_like_python_mapping_of_korml_values() -> None:
    first = korml.Scalar[korml.lexer.v1.Token](
        "first",
        cst=korml.CST(version=korml.Version.v1),
    )
    second = korml.Scalar[korml.lexer.v1.Token](
        "second",
        cst=korml.CST(version=korml.Version.v1),
    )

    mapping = korml.Mapping[korml.lexer.v1.Token](
        value_map={
            "a": first,
            "b": second,
        },
        cst=korml.CST(version=korml.Version.v1),
    )

    assert len(mapping) == 2
    assert mapping["a"] is first
    assert mapping["b"] is second
    assert list(mapping) == ["a", "b"]
    assert list(mapping.keys()) == ["a", "b"]
    assert list(mapping.values()) == [first, second]
    assert list(mapping.items()) == [("a", first), ("b", second)]
    assert mapping.to_builtin() == {
        "a": "first",
        "b": "second",
    }


def test_mapping_raw_assignment_converts_string_to_scalar() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    mapping["x"] = "g"

    assert isinstance(mapping["x"], korml.Scalar)
    assert mapping["x"].version is korml.Version.v1
    assert mapping.to_builtin() == {"x": "g"}


def test_mapping_raw_assignment_converts_nested_dicts_and_lists() -> None:
    b = {"c": "d"}

    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    mapping["s"] = {"a": b, "list": ["x", {"y": "z"}]}

    assert mapping.to_builtin() == {
        "s": {
            "a": {
                "c": "d",
            },
            "list": [
                "x",
                {
                    "y": "z",
                },
            ],
        },
    }

    assert mapping["s"].version is korml.Version.v1
    assert mapping["s"]["a"].version is korml.Version.v1  # type: ignore[index]
    assert mapping["s"]["list"].version is korml.Version.v1  # type: ignore[index]


def test_mapping_raw_assignment_rejects_existing_korml_value() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        mapping["x"] = korml.Scalar[korml.lexer.v1.Token](
            "g",
            cst=korml.CST(version=korml.Version.v1),
        )


def test_mapping_raw_assignment_rejects_non_string_key() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        mapping[1] = "g"  # type: ignore[index]


def test_mapping_raw_assignment_rejects_nested_non_string_key() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        mapping["x"] = {1: "g"}


def test_mapping_add_item_accepts_same_version_korml_value() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )
    value = korml.Scalar[korml.lexer.v1.Token](
        "g",
        cst=korml.CST(version=korml.Version.v1),
    )

    mapping.add_item("x", value)

    assert mapping["x"] is value
    assert mapping.to_builtin() == {"x": "g"}


def test_mapping_add_item_rejects_raw_value() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        mapping.add_item("x", "g")  # type: ignore[arg-type]


def test_mapping_add_item_rejects_wrong_version_korml_value() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )
    value = korml.Scalar[korml.lexer.v1.Token](
        "g",
        cst=korml.CST(version=korml.Version.unknown),
    )

    with pytest.raises(ValueError):
        mapping.add_item("x", value)


def test_mapping_add_item_rejects_non_string_key() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )
    value = korml.Scalar[korml.lexer.v1.Token](
        "g",
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        mapping.add_item(1, value)  # type: ignore[arg-type]


def test_mapping_constructor_rejects_wrong_version_child() -> None:
    with pytest.raises(ValueError):
        korml.Mapping[korml.lexer.v1.Token](
            value_map={
                "x": korml.Scalar[korml.lexer.v1.Token](
                    "g",
                    cst=korml.CST(version=korml.Version.unknown),
                )
            },
            cst=korml.CST(version=korml.Version.v1),
        )


def test_mapping_style_is_not_part_of_equality() -> None:
    flow = korml.Mapping[korml.lexer.v1.Token](
        style=korml.Style.flow,
    )
    block = korml.Mapping[korml.lexer.v1.Token](
        style=korml.Style.block,
    )

    assert flow == block


def test_mapping_missing_key_raises_key_error() -> None:
    mapping = korml.Mapping[korml.lexer.v1.Token]()

    with pytest.raises(KeyError):
        _ = mapping["missing"]


def test_stream_defaults_to_empty_stream() -> None:
    stream = korml.Stream[korml.lexer.v1.Token]()

    assert stream.version is korml.Version.unknown
    assert stream.filename == ""
    assert stream.document_array == []
    assert stream.token_array == ()
    assert stream.source == ""
    assert stream.span == korml.core.Span.empty()
    assert len(stream) == 0
    assert stream.to_builtin() == []


def test_stream_stores_documents_and_converts_to_builtin() -> None:
    first = korml.Scalar[korml.lexer.v1.Token](
        "first",
        cst=korml.CST(version=korml.Version.v1),
    )
    second = korml.Mapping[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )
    second["key"] = "value"

    stream = korml.Stream[korml.lexer.v1.Token](
        document_array=[first, second],
        filename="input.korml",
        cst=korml.CST(version=korml.Version.v1),
    )

    assert len(stream) == 2
    assert stream[0] is first
    assert stream[1] is second
    assert stream.filename == "input.korml"
    assert stream.to_builtin() == [
        "first",
        {
            "key": "value",
        },
    ]


def test_stream_preserves_cst_metadata() -> None:
    token_array = korml.lexer.v1.make_token_array(
        (korml.lexer.v1.TokenType.DOC_START, "---"),
        (korml.lexer.v1.TokenType.NEWLINE, "\n"),
        (korml.lexer.v1.TokenType.PLAIN_SCALAR, "first"),
        (korml.lexer.v1.TokenType.NEWLINE, "\n"),
        (korml.lexer.v1.TokenType.DOC_END, "..."),
        start=korml.core.make_position(
            line=1,
            column=1,
            offset=0,
        ),
    )

    stream = korml.Stream[korml.lexer.v1.Token](
        cst=korml.CST(
            version=korml.Version.v1,
            token_array=token_array,
        ),
    )

    assert stream.version is korml.Version.v1
    assert stream.token_array == token_array
    assert stream.source == "---\nfirst\n..."
    assert stream.span == korml.core.Span(
        start=token_array[0].span.start,
        end=token_array[-1].span.end,
    )


def test_stream_append_accepts_same_version_korml_value() -> None:
    stream = korml.Stream[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )
    value = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(version=korml.Version.v1),
    )

    stream.append(value)

    assert stream[0] is value
    assert stream.to_builtin() == ["hello"]


def test_stream_append_rejects_raw_value() -> None:
    stream = korml.Stream[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )

    with pytest.raises(TypeError):
        stream.append("hello")  # type: ignore[arg-type]


def test_stream_append_rejects_wrong_version_korml_value() -> None:
    stream = korml.Stream[korml.lexer.v1.Token](
        cst=korml.CST(version=korml.Version.v1),
    )
    value = korml.Scalar[korml.lexer.v1.Token](
        "hello",
        cst=korml.CST(version=korml.Version.unknown),
    )

    with pytest.raises(ValueError):
        stream.append(value)


def test_stream_constructor_rejects_wrong_version_document() -> None:
    with pytest.raises(ValueError):
        korml.Stream[korml.lexer.v1.Token](
            document_array=[
                korml.Scalar[korml.lexer.v1.Token](
                    "hello",
                    cst=korml.CST(version=korml.Version.unknown),
                )
            ],
            cst=korml.CST(version=korml.Version.v1),
        )


def test_version_values_are_stable() -> None:
    assert korml.Version.unknown.value == "unknown"
    assert korml.Version.v1.value == "v1"

    assert korml.Version("unknown") is korml.Version.unknown
    assert korml.Version("v1") is korml.Version.v1


def test_style_values_are_stable() -> None:
    assert korml.Style.auto.value == "auto"
    assert korml.Style.flow.value == "flow"
    assert korml.Style.block.value == "block"

    assert korml.Style("auto") is korml.Style.auto
    assert korml.Style("flow") is korml.Style.flow
    assert korml.Style("block") is korml.Style.block


def test_public_namespace_exposes_main_error_types_but_not_source_positions() -> None:
    assert korml.KormlError is korml.error.KormlError
    assert korml.LexError is korml.error.LexError
    assert korml.ParseError is korml.error.ParseError

    assert not hasattr(korml, "Position")
    assert not hasattr(korml, "Span")

    assert korml.core.Position is not None
    assert korml.core.Span is not None
