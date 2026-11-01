# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""
Core data structures for the korml library.

This module defines the small, shared objects used to describe source locations,
source ranges, and parser input text.

The main purpose of these structures is to keep parsed values connected to their
origin in the input. This allows korml to produce useful diagnostics, error
messages, and editor-friendly metadata without passing filenames, stream names,
line numbers, columns, and offsets around as separate values.

The module currently provides:

- Position:
    A concrete location in the input text.

- Span:
    A half-open range in the input text, represented by a start and end position.

- InputText:
    A string-like object carrying metadata about where the text came from.

- current_line:
    A small debugging/helper utility for recording the current Python source
    location.
"""

import dataclasses
import sys


@dataclasses.dataclass(frozen=True, slots=True)
class Position:
    """
    A concrete position in the source text.

    Coordinate conventions:
      - line is 1-based.
      - column is 1-based.
      - offset is 0-based absolute character offset from the start of the input.

    Invariants:
      - line, column, and offset refer to the same location in the same source
        text.
      - There is no fixed formula such as line * ncol + column == offset because
        lines may have different lengths.
      - The relationship is defined by the source text's line starts:

            offset == line_starts[line - 1] + (column - 1)

        where line_starts is the 0-based offset of each line's first character.

    Notes:
      - column is a textual column, meaning a codepoint index within the line
        plus one.
      - column is not a visual column. Tabs, combining characters, and Unicode
        grapheme clusters may render with different visual widths in editors.
    """

    line: int
    """The line, from 1."""
    column: int
    """The column, from 1, in code points."""
    offset: int
    """The offset from the start of the input, from 0, in code points."""

    def to_dict(self) -> dict:
        """
        Convert the position to a JSON-serializable dictionary.

        @return A dictionary with the line, column and offset.
        """
        return {
            "line": self.line,
            "column": self.column,
            "offset": self.offset,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Span:
    """
    A half-open source span [start, end).
    """

    start: Position
    """The position of the first character."""
    end: Position
    """The position after the last character."""

    @classmethod
    def empty(cls) -> "Span":
        """
        Return an empty span at the beginning of an input.

        The position follows the normal source-coordinate convention:

        - line is 1-based
        - column is 1-based
        - offset is 0-based

        @return The empty span at line 1, column 1.
        """
        position = Position(
            line=1,
            column=1,
            offset=0,
        )

        return cls(
            start=position,
            end=position,
        )

    def to_dict(self) -> dict:
        """
        Convert the span to a JSON-serializable dictionary.

        @return A dictionary with the start and end positions.
        """
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }

    def length(self) -> int:
        """
        Return the number of characters covered by the span.

        @return The number of characters.
        """
        return self.end.offset - self.start.offset


def current_line(*, stacklevel: int = 1) -> dict:
    """
    Return a JSON-serializable description of a Python source location.

    This helper is mainly useful for debugging, tracing, and reporting internal
    locations in korml itself.

    @param stacklevel The number of frames to walk upwards from this function: 1 for the immediate
        caller of current_line, 2 for its caller, and so on.

    @return A dictionary with the file, the line and the name of the function.
    """
    f = sys._getframe(stacklevel)
    return {
        "file": f.f_code.co_filename,
        "line": f.f_lineno,
        "function": f.f_code.co_name,
    }


def make_position(*, line: int, column: int, offset: int) -> Position:
    """
    Return the position with these coordinates.

    @param line The line, from 1.

    @param column The column, from 1, in code points.

    @param offset The offset from the start of the input, from 0, in code points.

    @return The position.
    """
    return Position(line=line, column=column, offset=offset)


def make_span(
    *,
    start_line: int,
    start_column: int,
    start_offset: int,
    end_line: int,
    end_column: int,
    end_offset: int,
) -> Span:
    """
    Return the span between two positions given by their coordinates.

    @param start_line The line of the start.

    @param start_column The column of the start.

    @param start_offset The offset of the start.

    @param end_line The line of the end.

    @param end_column The column of the end.

    @param end_offset The offset of the end.

    @return The span.
    """
    return Span(
        start=make_position(line=start_line, column=start_column, offset=start_offset),
        end=make_position(line=end_line, column=end_column, offset=end_offset),
    )


def advance_position(position: Position, value: str) -> Position:
    """
    Return the position after value, which starts at position.

    @param position The position where value starts.

    @param value The source text to move over.

    @return The position after the last character of value.
    """
    line = position.line
    column = position.column
    offset = position.offset

    # A line break is a line feed, a carriage return and line feed pair, or a
    # bare carriage return, as for the lexer, so every token on a line after a
    # bare carriage return gets its own line number.
    for index, char in enumerate(value):
        offset += 1

        if char == "\n" or (char == "\r" and value[index + 1 : index + 2] != "\n"):
            line += 1
            column = 1
        elif char != "\r":
            column += 1

    return Position(
        line=line,
        column=column,
        offset=offset,
    )
