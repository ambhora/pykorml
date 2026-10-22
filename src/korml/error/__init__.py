# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

"""Central exception hierarchy for korml.

This module defines the public exception hierarchy used by korml.

The hierarchy separates errors into two broad groups:

- BugError:
    An internal korml bug or inconsistent program state. These errors indicate
    that korml itself reached a situation that should not be possible during
    normal execution.

- CompilerError:
    An error caused while compiling, lexing, or parsing user-provided input.
    These errors are associated with an input source, such as a filename, stream
    name, or logical source name.

More specific compiler errors add progressively more context. For example,
LexError includes a concrete source span, while IndentationError specializes
LexError for indentation-related input problems.

The intended hierarchy is:

    KormlError
    ├── BugError
    └── CompilerError
        ├── LexError
        │   └── IndentationError
        └── ParseError
"""

import typing

import korml.core

__all__ = [
    "KormlError",
    "BaseError",
    "BugError",
    "CompilerError",
    "LexError",
    "IndentationError",
    "ParseError",
]


def escape_controls(text: str) -> str:
    """
    Represent unprintable characters, such as terminal controls, visibly.

    Diagnostics apply it to the fields that come from outside korml: the
    source name and the quoted source line. Messages are korml's own text;
    where they include text from the source or a schema, it is escaped where
    it is interpolated, so a message keeps its intended line breaks.
    structured() returns every field unmodified.
    """
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in text)


class KormlError(Exception):
    """
    Base class for all korml-defined exceptions.

    KormlError only stores information that is meaningful for every korml error:
    a human-readable message and, optionally, a machine-readable error code.

    This class is useful for catching all korml errors in one place:

        try:
            ...
        except korml.KormlError as error:
            ...

    Directly raising KormlError is allowed, but specific subclasses should be
    preferred whenever the error belongs to a more precise category.
    """

    def __init__(self, *, message: str, code: str | None = None):
        """
        Initialize a generic korml error.

        Args:
            message:
                Human-readable explanation of the error.

            code:
                Optional machine-readable error code. This is useful for tests,
                structured diagnostics, and downstream tools that should not
                depend on the exact wording of the message.
        """
        self._message = message
        self._code = code
        super().__init__(message)

    def message(self) -> str:
        """
        Return the human-readable error message.
        """
        return self._message

    def code(self) -> str | None:
        """
        Return the machine-readable error code, if one was provided.
        """
        return self._code

    def structured(self) -> dict[str, typing.Any]:
        """
        Return a structured, JSON-compatible representation of the error.

        The returned dictionary is intended for tests, diagnostics, language
        servers, editor integrations, and other tooling that should consume
        errors without parsing their formatted string representation.
        """
        return {
            "type": self.__class__.__name__,
            "code": self._code,
            "message": self._message,
        }

    def __str__(self) -> str:
        """
        Return describe(quote_source=True).
        """
        return self.describe(quote_source=True)

    def describe(self, *, quote_source: bool) -> str:
        """
        Return a human-readable representation of the error.

        With quote_source False, the description gives positions but no text
        of the source, for programs that must not print the content of what
        they read, such as configuration files holding secrets.
        """
        message = self._message
        if self._code is None:
            return f"{self.__class__.__name__}: {message}"

        return f"{self.__class__.__name__}: {message}\n  = code: {self._code}"


# Backward-compatible internal alias.  The public top-level name is
# ``korml.KormlError``; keeping ``korml.error.BaseError`` avoids breaking
# callers that already used the namespaced support module directly.
BaseError = KormlError


class BugError(KormlError):
    """
    Error raised when korml detects an internal bug.

    BugError should be used for situations that should not be reachable if korml
    is implemented correctly. This usually means an invalid internal state,
    violated invariant, unexpected control-flow path, or incorrect interaction
    between korml components.

    A BugError does not necessarily mean that the user input is invalid. It means
    korml failed to handle some situation correctly.
    """

    def __init__(
        self,
        *,
        message: str,
        location: str,
        details: str | None = None,
        source_name: str | None = None,
        span: korml.core.Span | None = None,
        source_line: str | None = None,
    ):
        # The summary is not stored as self.message, which would hide the
        # message() method every korml error has.
        self.summary = message
        self.location = location
        self.details = details
        self.source_name = source_name
        self.span = span
        self.source_line = source_line

        error_message = f"internal bug at {location}: {message}"

        if details is not None:
            error_message += f"\n\nDetails:\n{details}"

        if source_name is not None and span is not None:
            error_message += (
                f"\n\nSource location: {source_name}:{span.start.line}:{span.start.column}"
            )

        super().__init__(message=error_message)

    def describe(self, *, quote_source: bool) -> str:
        """
        Return the bug description, with the source line if quote_source.
        """
        text = super().describe(quote_source=quote_source)

        if quote_source and self.source_line is not None:
            text += f"\n\nSource line:\n{escape_controls(self.source_line)}"

        return text


class CompilerError(KormlError):
    """
    Base class for errors that occur while processing user input.

    CompilerError represents errors associated with a specific input source.
    The source may be a real file, standard input, an in-memory stream, or any
    other logical source understood by the caller.

    Subclasses add more precise context. For example, LexError adds a concrete
    Position, while ParseError can later be extended with token-level or grammar
    information.
    """

    def __init__(
        self,
        *,
        message: str,
        source_name: str,
        code: str | None = None,
    ):
        """
        Initialize an error associated with an input source.

        Args:
            message:
                Human-readable explanation of the error.

            source_name:
                Human-readable name of the input source. For files this is
                usually a path. For streams it may be a logical name such as
                "<stdin>", "<memory>", or another caller-provided label.

            code:
                Optional machine-readable error code.
        """
        self._source_name = source_name
        super().__init__(message=message, code=code)

    def source_name(self) -> str:
        """
        Return the human-readable name of the input source.
        """
        return self._source_name

    def structured(self) -> dict[str, typing.Any]:
        """
        Return a structured representation of the compiler error.

        The returned dictionary extends KormlError.structured() with the source
        name of the input being compiled.
        """
        data = super().structured()
        data["source_name"] = self._source_name
        return data

    def describe(self, *, quote_source: bool) -> str:
        """
        Return a human-readable compiler diagnostic.
        """
        lines = [
            f"{self.__class__.__name__}: {self._message}",
            f"  --> {escape_controls(self._source_name)}",
        ]

        if self._code is not None:
            lines.append(f"  = code: {self._code}")

        return "\n".join(lines)


class LexError(CompilerError):
    """
    Error raised for lexer-level problems in user input.

    LexError is used when the input text cannot be converted into a valid token
    stream. Examples include invalid characters, malformed literals, illegal
    indentation markers, or any other issue detected before parsing begins.

    A LexError carries a concrete korml.core.Span, allowing diagnostics to point
    to an exact source range.
    """

    def __init__(
        self,
        *,
        message: str,
        source_name: str,
        span: korml.core.Span,
        source_line: str | None = None,
        code: str | None = None,
    ):
        """
        Initialize a lexer error over a concrete source span.
        """
        self._span = span
        self._source_line = source_line
        super().__init__(
            message=message,
            source_name=source_name,
            code=code,
        )

    def span(self) -> korml.core.Span:
        """
        Return the source span where the lexer error occurred.
        """
        return self._span

    def source_line(self) -> str | None:
        """
        Return the full source line containing the error, if available.
        """
        return self._source_line

    def structured(self) -> dict[str, typing.Any]:
        """
        Return a structured representation of the lexer error.
        """
        data = super().structured()
        data["span"] = self._span.to_dict()
        data["source_line"] = self._source_line
        return data

    def describe(self, *, quote_source: bool) -> str:
        """
        Return a human-readable lexer diagnostic.
        """
        line = self._span.start.line
        column = self._span.start.column

        lines = [
            f"{self.__class__.__name__}: {self._message}",
            f"  --> {escape_controls(self._source_name)}:{line}:{column}",
        ]

        if quote_source and self._source_line is not None:
            start = max(0, column - 1)
            end = max(start + 1, self._span.end.column - 1)
            caret_offset = len(escape_controls(self._source_line[:start]))
            caret_width = max(1, len(escape_controls(self._source_line[start:end])))

            lines.extend(
                [
                    "  |",
                    f"{line} | {escape_controls(self._source_line)}",
                    f"  | {' ' * caret_offset}{'^' * caret_width}",
                ]
            )

        if self._code is not None:
            lines.append(f"  = code: {self._code}")

        return "\n".join(lines)


class IndentationError(LexError):
    """
    Error raised for indentation-related lexer problems.

    IndentationError is a specialized LexError used when the lexer detects an
    invalid indentation structure. Examples include inconsistent indentation,
    unexpected dedentation, or indentation in a location where indentation is not
    meaningful.

    This class intentionally inherits from LexError because indentation is
    usually resolved while converting raw text into tokens.
    """


class ParseError(CompilerError):
    """
    Error raised for parser-level problems in user input.

    ParseError is used when lexing succeeded sufficiently to produce a token
    stream, but the token stream does not satisfy the grammar expected by the
    parser. It carries the span of the token at fault when there is one, such
    as the repeated key of a duplicate entry, and None when the input ends
    where a value was expected.
    """

    def __init__(
        self,
        *,
        message: str,
        source_name: str,
        span: korml.core.Span | None,
        code: str | None = None,
    ):
        """
        Initialize a parser error, located at span if it is known.
        """
        self._span = span
        super().__init__(
            message=message,
            source_name=source_name,
            code=code,
        )

    def span(self) -> korml.core.Span | None:
        """
        Return the source span of the token at fault, if known.
        """
        return self._span

    def structured(self) -> dict[str, typing.Any]:
        """
        Return a structured representation of the parser error.
        """
        data = super().structured()
        data["span"] = None if self._span is None else self._span.to_dict()
        return data

    def describe(self, *, quote_source: bool) -> str:
        """
        Return a human-readable parser diagnostic.
        """
        location = self._source_name

        if self._span is not None:
            location += f":{self._span.start.line}:{self._span.start.column}"

        lines = [
            f"{self.__class__.__name__}: {self._message}",
            f"  --> {escape_controls(location)}",
        ]

        if self._code is not None:
            lines.append(f"  = code: {self._code}")

        return "\n".join(lines)
