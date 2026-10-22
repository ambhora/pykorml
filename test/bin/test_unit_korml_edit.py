# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""Replacing values of a parsed source while keeping everything else."""

import pytest

import korml

_SOURCE = (
    "# credentials\n"
    "token:\n"
    "  __keyloom__: secret  # wrapper\n"
    "  value: glpat-plain\n"
    "url: http://example.org:8080  # prod\n"
    "list:\n"
    "  - a   # first\n"
    "  - {k: v}\n"
)


def test_replacing_a_scalar_changes_only_its_tokens() -> None:
    stream = korml.loads(_SOURCE)
    token = stream[0]["token"]["value"]

    result = korml.edit(stream=stream, replacements=[(token, "$KEYLOOM;1;x")])

    assert result == _SOURCE.replace("glpat-plain", '"$KEYLOOM;1;x"')


def test_replacing_a_flow_scalar_keeps_the_flow_collection() -> None:
    stream = korml.loads(_SOURCE)

    result = korml.edit(stream=stream, replacements=[(stream[0]["list"][1]["k"], "w")])

    assert result == _SOURCE.replace("{k: v}", '{k: "w"}')


def test_replacing_a_block_mapping_puts_the_scalar_on_the_key_line() -> None:
    stream = korml.loads(_SOURCE)

    result = korml.edit(stream=stream, replacements=[(stream[0]["token"], "glpat-plain")])

    assert result == (
        "# credentials\n"
        'token: "glpat-plain"\n'
        "url: http://example.org:8080  # prod\n"
        "list:\n"
        "  - a   # first\n"
        "  - {k: v}\n"
    )


def test_replacement_text_is_quoted_so_it_cannot_become_structure() -> None:
    stream = korml.loads(_SOURCE)

    result = korml.edit(stream=stream, replacements=[(stream[0]["list"][0], "x\nadmin: true\n")])

    assert korml.loads(result).to_builtin()[0]["list"][0] == "x\nadmin: true\n"
    assert "admin" not in korml.loads(result).to_builtin()[0]


def test_v1_streams_keep_their_framing() -> None:
    source = "%!korml version 1.0\n---\na: 1  # one\n...\n---\nb: 2\n...\n"
    stream = korml.loads(source)

    result = korml.edit(stream=stream, replacements=[(stream[1]["b"], "3")])

    assert result == source.replace("b: 2", 'b: "3"')


def test_overlapping_replacements_are_rejected() -> None:
    stream = korml.loads(_SOURCE)
    token = stream[0]["token"]

    with pytest.raises(ValueError, match="overlap"):
        korml.edit(stream=stream, replacements=[(token, "a"), (token["value"], "b")])


def test_values_of_another_stream_are_rejected() -> None:
    stream = korml.loads(_SOURCE)
    other = korml.loads(_SOURCE)

    with pytest.raises(ValueError, match="not a value of this stream"):
        korml.edit(stream=stream, replacements=[(other[0]["url"], "x")])


def test_stream_loaded_without_limits_can_be_edited() -> None:
    source = "".join(f"k{i}: v{i}\n" for i in range(40_000))
    stream = korml.loads(source, max_tokens=None, max_parse_work=None)

    result = korml.edit(stream=stream, replacements=[(stream[0]["k1"], "x")])

    assert result == source.replace("k1: v1\n", 'k1: "x"\n', 1)
