# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import pytest

import korml
import korml.emitter.v0


def test_emit_v0_single_document_without_stream_framing() -> None:
    stream = korml.Stream(
        document_array=[
            korml.Mapping(
                value_map={
                    "a": korml.Scalar("b", cst=korml.CST(version=korml.Version.v0)),
                },
                cst=korml.CST(version=korml.Version.v0),
            )
        ],
        cst=korml.CST(version=korml.Version.v0),
    )

    assert korml.emitter.v0.emit(stream) == '"a": "b"\n'


def test_emit_v0_empty_stream_is_empty_source() -> None:
    stream = korml.Stream(cst=korml.CST(version=korml.Version.v0))

    assert korml.emitter.v0.emit(stream) == ""


def test_emit_v0_rejects_multiple_documents() -> None:
    stream = korml.Stream(
        document_array=[
            korml.Scalar("first", cst=korml.CST(version=korml.Version.v0)),
            korml.Scalar("second", cst=korml.CST(version=korml.Version.v0)),
        ],
        cst=korml.CST(version=korml.Version.v0),
    )

    with pytest.raises(ValueError, match="multiple documents"):
        korml.emitter.v0.emit(stream)


def test_emit_v0_rejects_v1_stream() -> None:
    stream = korml.Stream(cst=korml.CST(version=korml.Version.v1))

    with pytest.raises(ValueError, match="emitter v0 cannot emit"):
        korml.emitter.v0.emit(stream)


def test_unprintable_characters_are_escaped() -> None:
    value = {"a": "\x1b\x85\u2028\ufeff\x00x"}

    text = korml.dumps(value, version=korml.Version.v0)

    assert text == '"a": "\\x1b\\x85\\u2028\\ufeff\\0x"\n'
    assert korml.loads(text).to_builtin() == [value]


def test_lone_surrogate_cannot_be_emitted() -> None:
    with pytest.raises(ValueError, match="lone surrogate"):
        korml.dumps({"a": "\udcff"})
