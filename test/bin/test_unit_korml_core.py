# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import collections
import collections.abc
import dataclasses
import typing

import pytest

import korml.core

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_mock_span(start_offset: int, end_offset: int) -> korml.core.Span:
    """
    Generate a simple single-line span for testing.

    This helper intentionally treats column as offset+1, which is sufficient for
    unit tests that only need stable, distinct positions.
    """
    return korml.core.Span(
        start=korml.core.Position(line=1, column=start_offset + 1, offset=start_offset),
        end=korml.core.Position(line=1, column=end_offset + 1, offset=end_offset),
    )


def create_mock_span_at(
    line: int, start_col: int, start_off: int, end_col: int, end_off: int
) -> korml.core.Span:
    """
    Generate a span with explicit line/column and offset values.
    """
    return korml.core.Span(
        start=korml.core.Position(line=line, column=start_col, offset=start_off),
        end=korml.core.Position(line=line, column=end_col, offset=end_off),
    )


# ---------------------------------------------------------------------------
# 1) Position / Span integrity
# ---------------------------------------------------------------------------


def test_position_initialization():
    pos = korml.core.Position(line=10, column=5, offset=100)
    assert pos.line == 10
    assert pos.column == 5
    assert pos.offset == 100


def test_position_immutability():
    pos = korml.core.Position(line=1, column=1, offset=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pos.line = 2  # type: ignore[misc]


def test_position_hashable_and_equality():
    a = korml.core.Position(line=1, column=2, offset=3)
    b = korml.core.Position(line=1, column=2, offset=3)
    c = korml.core.Position(line=1, column=2, offset=4)

    assert a == b
    assert a != c
    assert hash(a) == hash(b)
    assert hash(a) != hash(c)


def test_span_properties():
    start = korml.core.Position(1, 1, 0)
    end = korml.core.Position(1, 5, 4)
    span = korml.core.Span(start, end)
    assert span.start == start
    assert span.end == end


def test_span_immutability():
    span = create_mock_span(0, 5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        span.start = korml.core.Position(1, 99, 99)  # type: ignore[misc]
