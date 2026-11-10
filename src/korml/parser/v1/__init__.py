# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc
import dataclasses
import enum

import korml._limits
import korml.core
import korml.error
import korml.lexer.v1
import korml.lexer.v1.file
import korml.model

__all__ = ["ErrorCode", "parse"]


class ErrorCode(str, enum.Enum):
    """The codes of the errors the parser reports."""

    EXPECTED_VALUE = "EXPECTED_VALUE"
    """A place that needs a value holds something else, or nothing."""
    EXPECTED_SCALAR = "EXPECTED_SCALAR"
    """A flow mapping key that is not a scalar."""
    EXPECTED_SEQUENCE = "EXPECTED_SEQUENCE"
    """A document that must be a sequence is not; only private helpers report it."""
    EXPECTED_MAPPING = "EXPECTED_MAPPING"
    """A document that must be a mapping is not; only private helpers report it."""
    EXPECTED_MAPPING_COLON = "EXPECTED_MAPPING_COLON"
    """A mapping key without its ':'."""
    UNEXPECTED_CONTENT = "UNEXPECTED_CONTENT"
    """Content the grammar does not allow where it stands."""
    DUPLICATE_KEY = "DUPLICATE_KEY"
    """A mapping key that repeats, compared as decoded strings."""
    TOO_DEEP = "TOO_DEEP"
    """Collections nested deeper than max_depth."""
    TOO_COMPLEX = "TOO_COMPLEX"
    """A source that needs more parser work than max_work."""
    INVALID_ESCAPE = "INVALID_ESCAPE"
    """A double-quoted scalar with an escape the rules do not define."""
    INVALID_INDENTATION = "INVALID_INDENTATION"
    """A line whose indentation does not fit the layout rules."""
    INVALID_BLOCK_SCALAR = "INVALID_BLOCK_SCALAR"
    """A block scalar whose lines break the indentation rules."""
    INVALID_KEY = "INVALID_KEY"
    """A key that is too long or holds a raw zero-width joiner."""
    MISSING_DOCUMENT_END = "MISSING_DOCUMENT_END"
    """A document without its '...'."""

    def __str__(self) -> str:
        """
        Return the code as text.

        @return The value of the code.
        """
        return self.value


# The default deepest nesting of collections the parser accepts; parse()
# takes the limit as max_depth. See korml._limits.
MAX_NESTING_DEPTH = korml._limits.MAX_NESTING_DEPTH
"""The default deepest nesting accepted; see korml._limits."""

# The longest key, in characters of source text, quotes included.
MAX_KEY_LENGTH = 1024
"""The longest key, in characters of source text, quotes included."""

_SCALAR_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.PLAIN_SCALAR,
    korml.lexer.v1.TokenType.SQ_SCALAR,
    korml.lexer.v1.TokenType.DQ_SCALAR,
    korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
    korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
}

_TRIVIA_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.WHITESPACE,
    korml.lexer.v1.TokenType.COMMENT,
    korml.lexer.v1.TokenType.NEWLINE,
}

# The escapes of double-quoted scalars: those of JSON, plus \UXXXXXXXX.
# Anything else written after a backslash is an error.
_DOUBLE_QUOTED_ESCAPE_MAP = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

# The escapes followed by a fixed number of hexadecimal digits.
_DOUBLE_QUOTED_HEX_ESCAPE_LENGTH_MAP = {"u": 4, "U": 8}

_FLOW_SCALAR_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.PLAIN_SCALAR,
    korml.lexer.v1.TokenType.SQ_SCALAR,
    korml.lexer.v1.TokenType.DQ_SCALAR,
}

_BLOCK_SCALAR_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
    korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
}

_FLOW_START_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
    korml.lexer.v1.TokenType.FLOW_MAPPING_START,
}

_FLOW_END_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
    korml.lexer.v1.TokenType.FLOW_MAPPING_END,
}

_STREAM_TOKEN_TYPE_SET = {
    korml.lexer.v1.TokenType.VERSION_DIRECTIVE,
    korml.lexer.v1.TokenType.DOC_START,
    korml.lexer.v1.TokenType.DOC_END,
    korml.lexer.v1.TokenType.EOF,
}


@dataclasses.dataclass
class _ParseBudget:
    remaining: int | None


def _check_tokens(file: korml.lexer.v1.File, max_tokens: int | None) -> None:
    """
    Raise a CompilerError if file has more tokens than max_tokens.

    @param file The tokenized file.

    @param max_tokens The largest number of tokens accepted, or None for no limit.
    """
    if max_tokens is not None and len(file.token_array) > max_tokens:
        raise korml.error.CompilerError(
            message=f"token count exceeds {max_tokens}",
            source_name=file.filename,
            code="TOO_MANY_TOKENS",
        )


def _check_flow_depth(
    file: korml.lexer.v1.File,
    max_depth: int | None = MAX_NESTING_DEPTH,
) -> None:
    """
    Reject excessive flow nesting before its recursive parsing work starts.

    @param file The tokenized file.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.
    """
    if max_depth is None:
        return

    depth = 0
    for token in file.token_array:
        if token.type in (
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
            korml.lexer.v1.TokenType.FLOW_MAPPING_START,
        ):
            depth += 1
            if depth > max_depth:
                raise _make_parse_error(
                    ErrorCode.TOO_DEEP,
                    message=korml._limits.too_deep_message(max_depth),
                    source_name=file.filename,
                    at=token,
                )
        elif token.type in (
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
            korml.lexer.v1.TokenType.FLOW_MAPPING_END,
        ):
            depth -= 1


def parse(
    file: korml.lexer.v1.File,
    *,
    max_tokens: int | None = korml._limits.MAX_TOKENS,
    max_work: int | None = korml._limits.MAX_PARSE_WORK,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    """
    Parse a tokenized v1 file into a stream of documents.

    A document without a root node, written '---' then '...', is an Empty
    in Stream.document_array, so the stream keeps every document.

    max_depth is the deepest nesting of collections accepted; deeper
    nesting is a ParseError with the code TOO_DEEP. None removes the limit,
    and nesting too deep for Python's recursion limit raises the same error.

    @param file The tokenized file, of version v1.

    @param max_tokens The largest number of tokens accepted, or None for no limit.

    @param max_work The largest amount of parser work accepted, or None for no limit.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The stream of documents.
    """
    if file.version is not korml.model.Version.v1:
        raise ValueError(f"parser v1 cannot parse version {file.version.value!r}")

    korml._limits.check_max_depth(max_depth)
    _check_tokens(file, max_tokens)
    _check_flow_depth(file, max_depth)
    budget = _ParseBudget(remaining=max_work)
    document_array: list[korml.model.Value[korml.lexer.v1.Token]] = []

    for document_token_array in _iter_document_body_token_arrays(
        file.token_array,
        source_name=file.filename,
    ):
        document_array.append(
            _parse_document(
                document_token_array,
                version=file.version,
                source_name=file.filename,
                budget=budget,
                max_depth=max_depth,
            )
        )

    return korml.model.Stream[korml.lexer.v1.Token](
        document_array=document_array,
        filename=file.filename,
        cst=korml.model.CST(
            version=file.version,
            token_array=file.token_array,
        ),
    )


def _parse_document(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
    budget: _ParseBudget | None,
    max_depth: int | None,
) -> korml.model.Value[korml.lexer.v1.Token]:
    """
    Parse one document body into its root value, or an Empty if it has none.

    A RecursionError, possible only when max_depth is None or larger than
    Python can recurse, becomes a ParseError with the code TOO_DEEP.

    @param token_array The concrete tokens of the document body.

    @param version The language version.

    @param source_name The name of the source, for diagnostics.

    @param budget The work left, shared between the documents of a source.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The root value, or an Empty.
    """
    try:
        root = _parse_body(
            token_array,
            version=version,
            source_name=source_name,
            depth=0,
            budget=budget,
            max_depth=max_depth,
        )
    except RecursionError as error:
        raise _make_parse_error(
            ErrorCode.TOO_DEEP,
            message=korml._limits.too_deep_message(max_depth),
            source_name=source_name,
            at=_first_non_trivia(token_array),
        ) from error

    if root is not None:
        return root

    return korml.model.Empty[korml.lexer.v1.Token](
        cst=korml.model.CST(version=version, token_array=tuple(token_array)),
    )


def _iter_document_body_token_arrays(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    source_name: str = "<unknown>",
) -> collections.abc.Iterator[tuple[korml.lexer.v1.Token, ...]]:
    """
    Yield the tokens between each '---' and its '...'.

    Outside documents only the directive and trivia may appear, and every
    document must be closed by '...'; the lexer guarantees both, and the
    parser checks them again for token arrays built by other means.

    @param token_array Every token of the source.

    @param source_name The name of the source, for diagnostics.

    @return The tokens of each document body.
    """
    in_document = False
    start = 0

    for index, token in enumerate(token_array):
        if token.type is korml.lexer.v1.TokenType.DOC_START and not in_document:
            in_document = True
            start = index + 1
            continue

        if token.type is korml.lexer.v1.TokenType.DOC_END and in_document:
            yield tuple(token_array[start:index])
            in_document = False
            continue

        if not in_document and token.type not in _TRIVIA_TOKEN_TYPE_SET | {
            korml.lexer.v1.TokenType.VERSION_DIRECTIVE
        }:
            raise _make_parse_error(
                ErrorCode.UNEXPECTED_CONTENT,
                message="unexpected content outside a document",
                source_name=source_name,
                at=token,
            )

    if in_document:
        raise _make_parse_error(
            ErrorCode.MISSING_DOCUMENT_END,
            message="document is not terminated by '...'",
            source_name=source_name,
            at=token_array[start - 1],
        )


def _parse_scalar(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Scalar[korml.lexer.v1.Token]:
    """
    Parse a token array that holds exactly one scalar token and trivia.

    A block scalar parsed on its own has no owner, so its content indentation
    is that of its first content line.

    @param token_array The tokens of the scalar.

    @param version The language version.

    @param source_name The name of the source, for diagnostics.

    @return The scalar.
    """
    concrete_token_array = tuple(token_array)
    semantic_token_array = _without_trivia(concrete_token_array)

    if len(semantic_token_array) != 1:
        raise _make_expected_scalar_error(
            source_name=source_name,
            token_array=concrete_token_array,
        )

    token = semantic_token_array[0]

    if token.type not in _SCALAR_TOKEN_TYPE_SET:
        raise _make_expected_scalar_error(
            source_name=source_name,
            token_array=concrete_token_array,
        )

    if token.type in _BLOCK_SCALAR_TOKEN_TYPE_SET:
        value, _ = _decode_block_scalar(token, owner_column=-1, width=None, source_name=source_name)
    else:
        value = _decode_flow_scalar(token, source_name=source_name)

    return korml.model.Scalar[korml.lexer.v1.Token](
        value,
        cst=korml.model.CST(
            version=version,
            token_array=concrete_token_array,
        ),
    )


def _without_trivia(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> tuple[korml.lexer.v1.Token, ...]:
    """
    Return the tokens that carry meaning.

    @param token_array The concrete tokens.

    @return The tokens, without whitespace, comments and line breaks.
    """
    return tuple(token for token in token_array if token.type not in _TRIVIA_TOKEN_TYPE_SET)


def _decode_flow_scalar(token: korml.lexer.v1.Token, *, source_name: str) -> str:
    """
    Return the string a plain, single-quoted or double-quoted scalar token denotes.

    @param token The scalar token.

    @param source_name The name of the source, for diagnostics.

    @return The string.
    """
    match token.type:
        case korml.lexer.v1.TokenType.PLAIN_SCALAR:
            return token.value

        case korml.lexer.v1.TokenType.SQ_SCALAR:
            return _parse_single_quoted_scalar_value(token.value)

        case korml.lexer.v1.TokenType.DQ_SCALAR:
            try:
                return _parse_double_quoted_scalar_value(token.value)
            except _EscapeError as error:
                raise _make_parse_error(
                    ErrorCode.INVALID_ESCAPE,
                    message=str(error),
                    source_name=source_name,
                    at=token,
                    unquoted_message=error.unquoted_message,
                ) from error

        case _:
            raise korml.error.BugError(
                message="unsupported scalar token type",
                location="korml.parser.v1._decode_flow_scalar",
                details=f"token type is {token.type!r}",
                span=token.span,
            )


def _parse_single_quoted_scalar_value(source: str) -> str:
    """
    Decode a single-quoted scalar.

    @param source The source text of the scalar, quotes included.

    @return The string.
    """
    return source[1:-1].replace("''", "'")


class _EscapeError(ValueError):
    """An escape in a double-quoted scalar that does not stand for a character."""

    def __init__(self, message: str, *, unquoted_message: str) -> None:
        """
        Initialize the error with its message and the message without the escape.

        @param message What is wrong, quoting the escape.

        @param unquoted_message What is wrong, without text of the source.
        """
        super().__init__(message)
        self.unquoted_message = unquoted_message


def _parse_double_quoted_scalar_value(source: str) -> str:
    """
    Decode a double-quoted scalar.

    The escapes are those of JSON plus \\UXXXXXXXX for code points beyond
    the Basic Multilingual Plane. An unknown escape, a malformed hexadecimal
    escape and an escape of a surrogate or of a code point above U+10FFFF
    are errors rather than text, so a value can never hold half of a
    character or something no encoder can write.

    @param source The source text of the scalar, quotes included.

    @return The string.
    """
    content = source[1:-1]
    output: list[str] = []
    index = 0

    while index < len(content):
        char = content[index]

        if char != "\\":
            output.append(char)
            index += 1
            continue

        escaped_char = content[index + 1 : index + 2]
        index += 2

        if escaped_char in _DOUBLE_QUOTED_ESCAPE_MAP:
            output.append(_DOUBLE_QUOTED_ESCAPE_MAP[escaped_char])
            continue

        length = _DOUBLE_QUOTED_HEX_ESCAPE_LENGTH_MAP.get(escaped_char)
        digits = content[index : index + length] if length is not None else ""

        if length is None or len(digits) != length or not _is_hex(digits):
            escape = "\\" + escaped_char
            raise _EscapeError(
                f"invalid escape {escape!r} in double-quoted scalar",
                unquoted_message="invalid escape in double-quoted scalar",
            )

        code_point = int(digits, 16)

        if 0xD800 <= code_point <= 0xDFFF or code_point > 0x10FFFF:
            escape = "\\" + escaped_char + digits
            raise _EscapeError(
                f"escape {escape!r} is not a Unicode scalar value",
                unquoted_message="escape is not a Unicode scalar value",
            )

        output.append(chr(code_point))
        index += length

    return "".join(output)


def _is_hex(text: str) -> bool:
    """
    Return whether text holds hexadecimal digits only.

    @param text The text.

    @return True if every character is a hexadecimal digit.
    """
    return all(char in "0123456789abcdefABCDEF" for char in text)


@dataclasses.dataclass(frozen=True, slots=True)
class _BlockScalarLine:
    """One line after the header of a block scalar."""

    text: str
    offset: int
    indentation: int
    is_empty: bool


def _split_block_scalar_lines(source: str) -> list[_BlockScalarLine]:
    """
    Split the lines after the header line of a block scalar token.

    @param source The source text of the token.

    @return The lines.
    """
    offset = _find_first_line_end(source)
    line_array: list[_BlockScalarLine] = []

    while offset < len(source):
        end = offset
        while end < len(source) and source[end] not in "\r\n":
            end += 1

        text = source[offset:end]
        indentation = len(text) - len(text.lstrip(" "))
        line_array.append(
            _BlockScalarLine(
                text=text,
                offset=offset,
                indentation=indentation,
                is_empty=indentation == len(text),
            )
        )

        offset = end + (2 if source.startswith("\r\n", end) else 1)

    return line_array


def _decode_block_scalar(
    token: korml.lexer.v1.Token,
    *,
    owner_column: int,
    width: int | None,
    source_name: str,
) -> tuple[str, int]:
    """
    Return the value of a block scalar token and the indentation width.

    The content indentation n is owner_column + width, where owner_column is
    the 0-based column of the key or dash the scalar is the value of. If the
    document has no indentation width yet, the first content line sets it.
    Every line is then checked against n:

    - a content line has at least n leading spaces and a character other
      than a space after them, and the first one has exactly n;
    - an empty line holds at most n spaces and nothing else;
    - any other line is an error.

    A literal value keeps every content line after its first n spaces, a
    folded value joins neighbouring lines with a space, and both end with
    exactly one line break; see the comments below for the details.

    @param token The block scalar token.

    @param owner_column The 0-based column of the key or dash, or -1 for none.

    @param width The indentation width of the document, or None if it is not fixed yet.

    @param source_name The name of the source, for diagnostics.

    @return The string and the indentation width.
    """
    line_array = _split_block_scalar_lines(token.value)
    first_content = next(
        (line for line in line_array if line.text.strip(" \t") != ""),
        None,
    )

    def fail(message: str, line: _BlockScalarLine | None = None) -> korml.error.ParseError:
        """
        Return the error for a problem in the scalar.

        @param message What is wrong.

        @param line The line at fault, or None for the start of the token.

        @return The error, with the code INVALID_BLOCK_SCALAR.
        """
        position = token.span.start
        if line is not None:
            position = korml.core.advance_position(position, token.value[: line.offset])
        return korml.error.ParseError(
            message=message,
            source_name=source_name,
            span=korml.core.Span(start=position, end=position),
            code=str(ErrorCode.INVALID_BLOCK_SCALAR),
        )

    if first_content is None:
        raise fail('block scalar has no content lines; write an empty string as ""')

    if width is None:
        width = first_content.indentation - owner_column

        if width <= 0:
            raise fail("block scalar content must be indented more than its key or dash")

    indent = owner_column + width
    content_index_array: list[int] = []

    for index, line in enumerate(line_array):
        if line.is_empty:
            if line.indentation > indent:
                raise fail(f"a blank line in a block scalar may hold at most {indent} spaces", line)
            continue

        if line.indentation < indent:
            if line.text.strip(" \t") == "":
                raise fail("a tab is not allowed in the indentation of a block scalar", line)

            raise fail(
                f"block scalar content must be indented by {indent} spaces, "
                f"found {line.indentation}",
                line,
            )

        if not content_index_array and line.indentation != indent:
            raise fail(
                f"the first line of a block scalar must be indented by exactly {indent} spaces, "
                f"found {line.indentation}",
                line,
            )

        content_index_array.append(index)

    first_index = content_index_array[0]
    last_index = content_index_array[-1]

    # Empty lines before the first content line are part of the value; the
    # empty lines after the last one are not, and the value ends with
    # exactly one line break, as YAML's default "clip" chomping does.
    leading = "\n" * first_index

    if token.type is korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR:
        body = "\n".join(
            "" if line.is_empty else line.text[indent:]
            for line in line_array[first_index : last_index + 1]
        )
        return leading + body + "\n", width

    # A folded scalar joins two content lines with one space when they are
    # neighbours, and with k line breaks when k empty lines separate them.
    # More-indented lines, which YAML keeps unfolded, are not allowed, so
    # every folded scalar reads the same in YAML.
    piece_array: list[str] = []
    previous_index: int | None = None

    for index in content_index_array:
        line = line_array[index]

        if line.indentation != indent or line.text[indent] == "\t":
            raise fail(
                f"every line of a folded block scalar must be indented by exactly {indent} "
                "spaces and start with a character other than a space or a tab",
                line,
            )

        if previous_index is not None:
            gap = index - previous_index - 1
            piece_array.append(" " if gap == 0 else "\n" * gap)

        piece_array.append(line.text[indent:])
        previous_index = index

    return leading + "".join(piece_array) + "\n", width


def _find_first_line_end(source: str) -> int:
    """
    Return the offset after the first line break.

    @param source The text to search.

    @return The offset, or the length of source if it has no line break.
    """
    index = 0

    while index < len(source):
        char = source[index]

        if char == "\r":
            if index + 1 < len(source) and source[index + 1] == "\n":
                return index + 2

            return index + 1

        if char == "\n":
            return index + 1

        index += 1

    return len(source)


def _make_expected_scalar_error(
    *,
    source_name: str,
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> korml.error.ParseError:
    """
    Return the error for tokens that are not one scalar.

    @param source_name The name of the source, for diagnostics.

    @param token_array The tokens that were read.

    @return The error, located at the token that should not be there.
    """
    semantic_token_array = _without_trivia(token_array)

    # Point at the token that should not be there, or at the one that is not
    # a scalar.
    if len(semantic_token_array) > 1:
        token = semantic_token_array[1]
    elif semantic_token_array:
        token = semantic_token_array[0]
    else:
        token = None

    return _make_parse_error(
        ErrorCode.EXPECTED_SCALAR,
        message="expected scalar",
        source_name=source_name,
        at=token,
    )


def _make_parse_error(
    code: ErrorCode,
    *,
    message: str,
    source_name: str,
    at: korml.lexer.v1.Token | None,
    unquoted_message: str | None = None,
) -> korml.error.ParseError:
    """
    Build a ParseError located at the token at, if there is one.

    @param code The error code.

    @param message What is wrong.

    @param source_name The name of the source, for diagnostics.

    @param at The token at fault, or None if there is none.

    @param unquoted_message What is wrong, without text of the source; None if message quotes
        none.

    @return The error.
    """
    return korml.error.ParseError(
        message=message,
        source_name=source_name,
        span=at.span if at is not None else None,
        code=str(code),
        unquoted_message=unquoted_message,
    )


def _first_non_trivia(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> korml.lexer.v1.Token | None:
    """
    Return the first token that carries meaning.

    @param token_array The concrete tokens.

    @return The token, or None if there is none.
    """
    for token in token_array:
        if token.type not in _TRIVIA_TOKEN_TYPE_SET:
            return token

    return None


# --------------------------------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------------------------------


class _Layout(enum.Enum):
    """The tokens the layout adds to the significant token stream."""

    NEWLINE = "NEWLINE"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    EOF = "EOF"


@dataclasses.dataclass(frozen=True, slots=True)
class _Event:
    """
    One token of the significant token stream the grammar is defined over.

    kind is the type of a concrete token, or a _Layout token. index is the
    position of the concrete token in the body's token array; for a layout
    token, the position of the concrete token it stands before (or the
    length of the array at the end of the body). token is the concrete
    token, used for diagnostics.
    """

    kind: korml.lexer.v1.TokenType | _Layout
    index: int
    token: korml.lexer.v1.Token | None


class _Layouter:
    """
    Turn the concrete tokens of a document body into the significant stream.

    This is the operational layout definition of the rules: a stack of
    open columns, initially [0], and an indentation width w that the first
    indented line (or the first block scalar) fixes for the whole document.
    Every content line must indent by exactly w more than the innermost
    open level, or dedent to an open level. A sequence dash followed by
    content on its line opens a compact level two columns right of the
    dash. Blank lines, block scalar content lines and the continuation
    lines of a flow collection take no part. Block scalars are decoded here,
    because their content indentation depends on w.
    """

    def __init__(
        self,
        token_array: tuple[korml.lexer.v1.Token, ...],
        *,
        source_name: str,
    ) -> None:
        """
        Prepare to read the tokens of one document body.

        @param token_array The concrete tokens of the document body.

        @param source_name The name of the source, for diagnostics.
        """
        self.token_array = token_array
        self.source_name = source_name
        self.event_array: list[_Event] = []
        self.block_scalar_value_map: dict[int, str] = {}
        self.stack = [0]
        self.width: int | None = None
        self.significant_index_array: list[int] = []

    def error(
        self,
        code: ErrorCode,
        message: str,
        token: korml.lexer.v1.Token | None,
    ) -> korml.error.ParseError:
        """
        Return a ParseError located at a token.

        @param code The error code.

        @param message What is wrong.

        @param token The token at fault, or None if there is none.

        @return The error.
        """
        return _make_parse_error(code, message=message, source_name=self.source_name, at=token)

    def run(self) -> list[_Event]:
        """
        Turn the tokens into the significant stream, and decode the block scalars.

        @return The significant stream.
        """
        at_line_start = True
        open_content_line = False
        flow_depth = 0
        flow_owner_column = -1

        for index, token in enumerate(self.token_array):
            kind = token.type

            if kind in (korml.lexer.v1.TokenType.WHITESPACE, korml.lexer.v1.TokenType.COMMENT):
                continue

            if kind is korml.lexer.v1.TokenType.NEWLINE:
                if flow_depth == 0 and open_content_line:
                    self.event_array.append(_Event(_Layout.NEWLINE, index, token))
                    open_content_line = False
                at_line_start = True
                continue

            if kind in _STREAM_TOKEN_TYPE_SET:
                raise self.error(
                    ErrorCode.UNEXPECTED_CONTENT,
                    f"unexpected {token.value!r} in a document body",
                    token,
                )

            column = token.span.start.column - 1

            if at_line_start and flow_depth == 0:
                self.open_content_line(index, token, column)
                open_content_line = True
            elif at_line_start and column <= flow_owner_column:
                raise self.error(
                    ErrorCode.INVALID_INDENTATION,
                    "a continuation line of a flow collection must be indented more than "
                    f"its key or dash (column {flow_owner_column + 1})",
                    token,
                )

            at_line_start = False
            self.event_array.append(_Event(kind, index, token))

            if kind is korml.lexer.v1.TokenType.DASH_ITEM and flow_depth == 0:
                self.open_compact_level(index, token, column)
            elif kind in _FLOW_START_TOKEN_TYPE_SET:
                if flow_depth == 0:
                    owner_column = self.owner_column()
                    flow_owner_column = -1 if owner_column is None else owner_column
                flow_depth += 1
            elif kind in _FLOW_END_TOKEN_TYPE_SET:
                flow_depth = max(0, flow_depth - 1)
            elif kind in _BLOCK_SCALAR_TOKEN_TYPE_SET:
                self.decode_block_scalar(index, token)
                # The token holds its header line break and its content
                # lines; no NEWLINE follows it.
                open_content_line = False
                at_line_start = True

            self.significant_index_array.append(index)

        if open_content_line:
            self.event_array.append(_Event(_Layout.NEWLINE, len(self.token_array), None))

        while len(self.stack) > 1:
            self.stack.pop()
            self.event_array.append(_Event(_Layout.DEDENT, len(self.token_array), None))

        self.event_array.append(_Event(_Layout.EOF, len(self.token_array), None))

        return self.event_array

    def open_content_line(self, index: int, token: korml.lexer.v1.Token, column: int) -> None:
        """
        Add the layout tokens for the first token of a line.

        @param index The position of the token in the body.

        @param token The token.

        @param column The 0-based column of the token.
        """
        top = self.stack[-1]

        if column > top:
            if self.width is None:
                self.width = column - top

            if column != top + self.width:
                raise self.error(
                    ErrorCode.INVALID_INDENTATION,
                    f"expected indentation of {top + self.width} spaces, found {column}; "
                    f"this document indents each level by {self.width} spaces",
                    token,
                )

            self.stack.append(column)
            self.event_array.append(_Event(_Layout.INDENT, index, token))
            return

        while self.stack[-1] > column:
            self.stack.pop()
            self.event_array.append(_Event(_Layout.DEDENT, index, token))

        if self.stack[-1] != column:
            raise self.error(
                ErrorCode.INVALID_INDENTATION,
                f"indentation of {column} spaces does not match any enclosing level",
                token,
            )

    def open_compact_level(self, index: int, token: korml.lexer.v1.Token, column: int) -> None:
        """
        Open the level of a compact entry, as in '- key: value' or '- - a'.

        @param index The position of the dash in the body.

        @param token The dash.

        @param column The 0-based column of the dash.
        """
        content_index = index + 1

        while (
            content_index < len(self.token_array)
            and self.token_array[content_index].type is korml.lexer.v1.TokenType.WHITESPACE
        ):
            content_index += 1

        if content_index >= len(self.token_array) or self.token_array[content_index].type in (
            korml.lexer.v1.TokenType.NEWLINE,
            korml.lexer.v1.TokenType.COMMENT,
        ):
            return

        content = self.token_array[content_index]

        if content.span.start.column - 1 != column + 2:
            raise self.error(
                ErrorCode.INVALID_INDENTATION,
                "exactly one space must separate a sequence dash from the content after it",
                content,
            )

        self.stack.append(column + 2)
        self.event_array.append(_Event(_Layout.INDENT, content_index, content))

    def owner_column(self) -> int | None:
        """
        Return the column of the key or dash whose value starts at the next token.

        That is the key before a ':' or the dash before the value; None if
        the value is not the value of an entry (the root node, or a place
        the grammar rejects).

        @return The 0-based column, or None.
        """
        if not self.significant_index_array:
            return None

        previous = self.token_array[self.significant_index_array[-1]]

        if previous.type is korml.lexer.v1.TokenType.DASH_ITEM:
            return previous.span.start.column - 1

        if (
            previous.type is korml.lexer.v1.TokenType.COLON
            and len(self.significant_index_array) >= 2
        ):
            key = self.token_array[self.significant_index_array[-2]]
            return key.span.start.column - 1

        return None

    def decode_block_scalar(self, index: int, token: korml.lexer.v1.Token) -> None:
        """
        Decode a block scalar, which needs the layout for its indentation.

        @param index The position of the token in the body.

        @param token The block scalar token.
        """
        owner_column = self.owner_column()

        # A block scalar that is not the value of an entry is an error the
        # grammar reports; it is not decoded, so it cannot fix the width.
        if owner_column is None:
            return

        value, self.width = _decode_block_scalar(
            token,
            owner_column=owner_column,
            width=self.width,
            source_name=self.source_name,
        )
        self.block_scalar_value_map[index] = value


# --------------------------------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------------------------------


_SCALAR_KIND_MAP = {
    korml.lexer.v1.TokenType.PLAIN_SCALAR: "plain scalar content",
    korml.lexer.v1.TokenType.SQ_SCALAR: "single-quoted scalar content",
    korml.lexer.v1.TokenType.DQ_SCALAR: "double-quoted scalar content",
    korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR: "literal block scalar content",
    korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR: "folded block scalar content",
}
"""How a message names a scalar token when it must not quote the source."""


def _describe_event(event: _Event, *, quote: bool = True) -> str:
    """
    Describe a token for a message such as "unexpected <description>".

    @param event The token.

    @param quote Whether the description may quote the text of a scalar token; without it, a
        scalar is named by its kind, and only syntax tokens are quoted.

    @return The description.
    """
    match event.kind:
        case _Layout.NEWLINE:
            return "end of line"
        case _Layout.INDENT:
            return "indentation"
        case _Layout.DEDENT:
            return "end of the indented block"
        case _Layout.EOF:
            return "end of document"
        case _:
            assert event.token is not None
            if not quote and event.kind in _SCALAR_KIND_MAP:
                return _SCALAR_KIND_MAP[event.kind]
            return f"content {event.token.value!r}"


class _Parser:
    """
    A recursive-descent parser for the grammar of a document body.

    It reads the significant token stream from _Layouter. Each value it
    builds keeps, as its CST, the concrete tokens from just after the
    indicator before it (':', '-', '[', '{' or ',') up to the next
    significant token after it, so comments and line breaks after a value
    belong to that value.
    """

    def __init__(
        self,
        token_array: tuple[korml.lexer.v1.Token, ...],
        *,
        version: korml.model.Version,
        source_name: str,
        budget: _ParseBudget | None,
        max_depth: int | None = MAX_NESTING_DEPTH,
    ) -> None:
        """
        Run the layout over the tokens of one document body.

        @param token_array The concrete tokens of the document body.

        @param version The language version.

        @param source_name The name of the source, for diagnostics.

        @param budget The work left, shared between the documents of a source.

        @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
            korml.
        """
        layouter = _Layouter(token_array, source_name=source_name)
        self.event_array = layouter.run()
        self.block_scalar_value_map = layouter.block_scalar_value_map
        self.token_array = token_array
        self.version = version
        self.source_name = source_name
        self.budget = budget
        self.max_depth = max_depth
        self.position = 0

    # Token access -------------------------------------------------------------------------------

    def peek(self, offset: int = 0) -> _Event:
        """
        Return a token ahead, without consuming it.

        @param offset How many tokens ahead.

        @return The token, or the last one if that is past the end.
        """
        index = min(self.position + offset, len(self.event_array) - 1)
        return self.event_array[index]

    def advance(self) -> _Event:
        """
        Consume a token and spend one unit of the work budget.

        @return The token consumed.
        """
        event = self.event_array[self.position]

        if self.budget is not None and self.budget.remaining is not None:
            self.budget.remaining -= 1
            if self.budget.remaining < 0:
                raise self.error(
                    ErrorCode.TOO_COMPLEX, "document exceeds parser work budget", event
                )

        if event.kind is not _Layout.EOF:
            self.position += 1

        return event

    def error(
        self,
        code: ErrorCode,
        message: str | collections.abc.Callable[[str], str],
        event: _Event,
    ) -> korml.error.ParseError:
        """
        Return a ParseError located at a token.

        @param code The error code.

        @param message What is wrong; or a function that says what is wrong given a description
            of the token, called once with a description that quotes it and once with one that
            does not, for describe(quote_source=False).

        @param event The token at fault.

        @return The error.
        """
        unquoted_message = None

        if callable(message):
            unquoted_message = message(_describe_event(event, quote=False))
            message = message(_describe_event(event))

        return _make_parse_error(
            code,
            message=message,
            source_name=self.source_name,
            at=event.token,
            unquoted_message=unquoted_message,
        )

    def expect(self, kind: _Layout, after: str) -> None:
        """
        Consume a layout token, or raise a ParseError if another comes next.

        @param kind The layout token that must come next.

        @param after What it follows, for the message.
        """
        event = self.peek()

        if event.kind is not kind:
            raise self.error(
                ErrorCode.UNEXPECTED_CONTENT,
                lambda what: f"unexpected {what} after {after}",
                event,
            )

        self.advance()

    def range_end(self) -> int:
        """
        Return the index of the next concrete significant token, or the end of the body.

        @return The index.
        """
        # Only layout tokens can come before the next concrete token, and at
        # most a few of them per line, so this does not slice the stream.
        for index in range(self.position, len(self.event_array)):
            event = self.event_array[index]
            if not isinstance(event.kind, _Layout):
                return event.index

        return len(self.token_array)

    def cst(self, start: int) -> korml.model.CST[korml.lexer.v1.Token]:
        """
        Return the CST from a token up to the next significant token.

        @param start The index of the first token of the value's CST.

        @return The CST.
        """
        return korml.model.CST(
            version=self.version,
            token_array=self.token_array[start : self.range_end()],
        )

    def check_depth(self, depth: int, event: _Event) -> None:
        """
        Refuse a collection inside depth others if that breaks max_depth.

        @param depth The number of collections around this one.

        @param event The token that opens the collection.
        """
        if korml._limits.is_too_deep(depth, self.max_depth):
            raise self.error(
                ErrorCode.TOO_DEEP,
                korml._limits.too_deep_message(self.max_depth),
                event,
            )

    def is_mapping_entry_start(self) -> bool:
        """
        Return whether a key and its colon come next.

        @return True if a mapping entry starts here.
        """
        return (
            self.peek().kind in _FLOW_SCALAR_TOKEN_TYPE_SET
            and self.peek(1).kind is korml.lexer.v1.TokenType.COLON
        )

    # Body ---------------------------------------------------------------------------------------

    def parse_body(self, depth: int) -> korml.model.Value[korml.lexer.v1.Token] | None:
        """
        Body ::= RootNode, or nothing at all for an empty document.

        @param depth The number of collections around the root.

        @return The root value, or None for an empty document.
        """
        if self.peek().kind is _Layout.EOF:
            return None

        root = self.parse_root(depth)
        event = self.peek()

        if event.kind is not _Layout.EOF:
            raise self.error(
                ErrorCode.UNEXPECTED_CONTENT,
                lambda what: f"unexpected {what} after the root node",
                event,
            )

        return root

    def parse_root(self, depth: int) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        RootNode ::= BlockMapping | BlockSequence | FlowNode NEWLINE | FlowScalar NEWLINE

        @param depth The number of collections around the root.

        @return The root value.
        """
        event = self.peek()

        if event.kind is _Layout.INDENT:
            raise self.error(
                ErrorCode.INVALID_INDENTATION,
                "the root node must start at column 1",
                event,
            )

        if event.kind in _BLOCK_SCALAR_TOKEN_TYPE_SET:
            raise self.error(
                ErrorCode.EXPECTED_VALUE,
                "a block scalar cannot be the root node; write the value double-quoted",
                event,
            )

        if event.kind is korml.lexer.v1.TokenType.DASH_ITEM or self.is_mapping_entry_start():
            return self.parse_block_node(0, depth)

        return self.parse_inline_value(0, depth, after="the root node")

    # Block collections --------------------------------------------------------------------------

    def parse_block_node(self, start: int, depth: int) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        BlockNode ::= BlockMapping | BlockSequence

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The value.
        """
        event = self.peek()

        if event.kind is korml.lexer.v1.TokenType.DASH_ITEM:
            return self.parse_block_sequence(start, depth)

        if self.is_mapping_entry_start():
            return self.parse_block_mapping(start, depth)

        raise self.error(
            ErrorCode.EXPECTED_VALUE,
            lambda what: (
                f"expected a block mapping or sequence, found {what}; "
                "a scalar or flow collection goes on the line of its key or dash"
            ),
            event,
        )

    def parse_block_mapping(
        self, start: int, depth: int
    ) -> korml.model.Mapping[korml.lexer.v1.Token]:
        """
        BlockMapping ::= MappingEntry+ ; MappingEntry ::= Key COLON EntryValue

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The mapping.
        """
        self.check_depth(depth, self.peek())
        mapping = korml.model.Mapping[korml.lexer.v1.Token](
            style=korml.model.Style.block,
            cst=korml.model.CST(version=self.version),
        )

        while self.peek().kind not in (_Layout.DEDENT, _Layout.EOF):
            event = self.peek()

            if event.kind not in _FLOW_SCALAR_TOKEN_TYPE_SET:
                raise self.error(
                    ErrorCode.UNEXPECTED_CONTENT,
                    lambda what: f"unexpected {what}; expected a mapping key",
                    event,
                )

            if self.peek(1).kind is not korml.lexer.v1.TokenType.COLON:
                raise self.error(
                    ErrorCode.EXPECTED_MAPPING_COLON,
                    "expected ':' after mapping key",
                    event,
                )

            key_event = self.advance()
            colon_event = self.advance()
            key = self.decode_key(key_event)
            value = self.parse_entry_value(colon_event.index + 1, depth + 1, key_event)
            _add_unique_item(
                mapping, key, value, key_token=key_event.token, source_name=self.source_name
            )

        mapping.cst = self.cst(start)
        return mapping

    def parse_entry_value(
        self, start: int, depth: int, key_event: _Event
    ) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        EntryValue ::= InlineValue NEWLINE | BlockScalar | NEWLINE INDENT BlockNode DEDENT

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @param key_event The key of the entry.

        @return The value.
        """
        event = self.peek()

        if event.kind is _Layout.NEWLINE:
            self.advance()
            return self.parse_indented_block_node(start, depth, key_event)

        if event.kind in _BLOCK_SCALAR_TOKEN_TYPE_SET:
            return self.parse_block_scalar(start)

        if event.kind is korml.lexer.v1.TokenType.DASH_ITEM:
            raise self.error(
                ErrorCode.EXPECTED_VALUE,
                "a block sequence cannot start on the line of its key; "
                "start it on the next line, indented",
                event,
            )

        return self.parse_inline_value(start, depth, after="the value of a mapping entry")

    def parse_indented_block_node(
        self, start: int, depth: int, owner_event: _Event
    ) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        The NEWLINE INDENT BlockNode DEDENT part of an entry, after its NEWLINE.

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @param owner_event The key or dash of the entry.

        @return The value.
        """
        event = self.peek()

        if event.kind is not _Layout.INDENT:
            owner = "key" if owner_event.kind is not korml.lexer.v1.TokenType.DASH_ITEM else "dash"
            message = f"expected a value after the {owner}"

            if event.kind is korml.lexer.v1.TokenType.DASH_ITEM:
                message = "a sequence that is the value of a key must be indented more than the key"

            raise self.error(ErrorCode.EXPECTED_VALUE, message, owner_event)

        self.advance()
        value = self.parse_block_node(start, depth)
        self.expect(_Layout.DEDENT, "block node")
        return value

    def parse_block_sequence(
        self, start: int, depth: int
    ) -> korml.model.Sequence[korml.lexer.v1.Token]:
        """
        BlockSequence ::= SequenceEntry+
        SequenceEntry ::= DASH_ITEM INDENT CompactValue DEDENT
                        | DASH_ITEM NEWLINE INDENT BlockNode DEDENT

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The sequence.
        """
        self.check_depth(depth, self.peek())
        value_array: list[korml.model.Value[korml.lexer.v1.Token]] = []

        while self.peek().kind not in (_Layout.DEDENT, _Layout.EOF):
            event = self.peek()

            if event.kind is not korml.lexer.v1.TokenType.DASH_ITEM:
                raise self.error(
                    ErrorCode.UNEXPECTED_CONTENT,
                    lambda what: f"unexpected {what}; expected a sequence entry",
                    event,
                )

            dash_event = self.advance()
            value_start = dash_event.index + 1
            event = self.peek()

            if event.kind is _Layout.INDENT:
                self.advance()
                value_array.append(self.parse_compact_value(value_start, depth + 1))
                self.expect(_Layout.DEDENT, "sequence entry")
            elif event.kind is _Layout.NEWLINE:
                self.advance()
                value_array.append(
                    self.parse_indented_block_node(value_start, depth + 1, dash_event)
                )
            else:
                raise self.error(
                    ErrorCode.EXPECTED_VALUE, "expected a value after the dash", dash_event
                )

        return korml.model.Sequence[korml.lexer.v1.Token](
            value_array=value_array,
            style=korml.model.Style.block,
            cst=self.cst(start),
        )

    def parse_compact_value(
        self, start: int, depth: int
    ) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        CompactValue ::= BlockMapping | BlockSequence | InlineValue NEWLINE | BlockScalar

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The value.
        """
        event = self.peek()

        if event.kind is korml.lexer.v1.TokenType.DASH_ITEM or self.is_mapping_entry_start():
            return self.parse_block_node(start, depth)

        if event.kind in _BLOCK_SCALAR_TOKEN_TYPE_SET:
            return self.parse_block_scalar(start)

        return self.parse_inline_value(start, depth, after="the value of a sequence entry")

    def parse_inline_value(
        self, start: int, depth: int, *, after: str
    ) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        InlineValue NEWLINE, where InlineValue ::= FlowNode | FlowScalar

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @param after What the value is, for the message.

        @return The value.
        """
        value = self.parse_flow_value(start, depth)
        self.expect(_Layout.NEWLINE, after)
        return value

    # Scalars ------------------------------------------------------------------------------------

    def parse_block_scalar(self, start: int) -> korml.model.Scalar[korml.lexer.v1.Token]:
        """
        Build the value of a block scalar the layout decoded.

        @param start The index of the first token of the value's CST.

        @return The scalar.
        """
        event = self.advance()
        value = self.block_scalar_value_map.get(event.index)

        if value is None:
            raise korml.error.BugError(
                message="block scalar was not decoded by the layout",
                location="korml.parser.v1._Parser.parse_block_scalar",
                span=event.token.span if event.token is not None else None,
            )

        return korml.model.Scalar[korml.lexer.v1.Token](value, cst=self.cst(start))

    def parse_flow_scalar(self, start: int) -> korml.model.Scalar[korml.lexer.v1.Token]:
        """
        Decode a plain or quoted scalar.

        @param start The index of the first token of the value's CST.

        @return The scalar.
        """
        event = self.advance()
        assert event.token is not None
        value = _decode_flow_scalar(event.token, source_name=self.source_name)
        return korml.model.Scalar[korml.lexer.v1.Token](value, cst=self.cst(start))

    def decode_key(self, event: _Event) -> str:
        """
        Return the string a key denotes, checking the rules for keys.

        A key is at most MAX_KEY_LENGTH characters of source text and holds
        no raw zero-width joiner or non-joiner, which would make two
        different keys look the same; it may hold them as escapes.

        @param event The key token.

        @return The string.
        """
        token = event.token
        assert token is not None

        if len(token.value) > MAX_KEY_LENGTH:
            raise self.error(
                ErrorCode.INVALID_KEY,
                f"key is longer than {MAX_KEY_LENGTH} characters",
                event,
            )

        joiner = next(
            (char for char in token.value if char in korml.lexer.v1.file.JOINER_CHARACTER_SET),
            None,
        )

        if joiner is not None:
            raise self.error(
                ErrorCode.INVALID_KEY,
                f"key contains U+{ord(joiner):04X} raw; write it as an escape in a "
                "double-quoted key",
                event,
            )

        return _decode_flow_scalar(token, source_name=self.source_name)

    # Flow collections ---------------------------------------------------------------------------

    def parse_flow_value(self, start: int, depth: int) -> korml.model.Value[korml.lexer.v1.Token]:
        """
        FlowValue ::= FlowNode | FlowScalar

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The value.
        """
        event = self.peek()

        if event.kind is korml.lexer.v1.TokenType.FLOW_SEQUENCE_START:
            return self.parse_flow_sequence(start, depth)

        if event.kind is korml.lexer.v1.TokenType.FLOW_MAPPING_START:
            return self.parse_flow_mapping(start, depth)

        if event.kind in _FLOW_SCALAR_TOKEN_TYPE_SET:
            return self.parse_flow_scalar(start)

        if event.kind in _BLOCK_SCALAR_TOKEN_TYPE_SET:
            raise self.error(
                ErrorCode.EXPECTED_VALUE,
                "a block scalar can only be the value of a block mapping or sequence entry",
                event,
            )

        if event.kind is korml.lexer.v1.TokenType.FLOW_SEPARATOR:
            raise self.error(ErrorCode.EXPECTED_VALUE, "missing entry before flow separator", event)

        if event.kind in _FLOW_END_TOKEN_TYPE_SET:
            raise self.error(
                ErrorCode.EXPECTED_VALUE, "a flow collection cannot end with ','", event
            )

        raise self.error(
            ErrorCode.EXPECTED_VALUE, lambda what: f"expected value, found {what}", event
        )

    def parse_flow_sequence(
        self, start: int, depth: int
    ) -> korml.model.Sequence[korml.lexer.v1.Token]:
        """
        FlowSequence ::= '[' (FlowValue (',' FlowValue)*)? ']'

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The sequence.
        """
        open_event = self.advance()
        self.check_depth(depth, open_event)
        value_array: list[korml.model.Value[korml.lexer.v1.Token]] = []

        if self.peek().kind is korml.lexer.v1.TokenType.FLOW_SEQUENCE_END:
            self.advance()
        else:
            item_start = open_event.index + 1

            while True:
                value_array.append(self.parse_flow_value(item_start, depth + 1))
                event = self.advance()

                if event.kind is korml.lexer.v1.TokenType.FLOW_SEQUENCE_END:
                    break

                if event.kind is not korml.lexer.v1.TokenType.FLOW_SEPARATOR:
                    raise self.error(
                        ErrorCode.UNEXPECTED_CONTENT,
                        lambda what: f"unexpected {what}; expected ',' or ']' in flow sequence",
                        event,
                    )

                item_start = event.index + 1

        return korml.model.Sequence[korml.lexer.v1.Token](
            value_array=value_array,
            style=korml.model.Style.flow,
            cst=self.cst(start),
        )

    def parse_flow_mapping(
        self, start: int, depth: int
    ) -> korml.model.Mapping[korml.lexer.v1.Token]:
        """
        FlowMapping ::= '{' (FlowEntry (',' FlowEntry)*)? '}'
        FlowEntry   ::= Key COLON FlowValue

        @param start The index of the first token of the value's CST.

        @param depth The number of collections around this value.

        @return The mapping.
        """
        open_event = self.advance()
        self.check_depth(depth, open_event)
        mapping = korml.model.Mapping[korml.lexer.v1.Token](
            style=korml.model.Style.flow,
            cst=korml.model.CST(version=self.version),
        )

        if self.peek().kind is korml.lexer.v1.TokenType.FLOW_MAPPING_END:
            self.advance()
        else:
            while True:
                key_event = self.peek()

                if key_event.kind is korml.lexer.v1.TokenType.FLOW_SEPARATOR:
                    raise self.error(
                        ErrorCode.EXPECTED_VALUE, "missing entry before flow separator", key_event
                    )

                if key_event.kind is korml.lexer.v1.TokenType.FLOW_MAPPING_END:
                    raise self.error(
                        ErrorCode.EXPECTED_VALUE, "a flow collection cannot end with ','", key_event
                    )

                if key_event.kind not in _FLOW_SCALAR_TOKEN_TYPE_SET:
                    raise self.error(
                        ErrorCode.EXPECTED_SCALAR,
                        lambda what: f"a flow mapping key must be a scalar, found {what}",
                        key_event,
                    )

                self.advance()

                colon_event = self.peek()

                if colon_event.kind is not korml.lexer.v1.TokenType.COLON:
                    raise self.error(
                        ErrorCode.EXPECTED_MAPPING_COLON,
                        "expected ':' after flow mapping key",
                        key_event,
                    )

                self.advance()
                key = self.decode_key(key_event)
                value_event = self.peek()
                line_array = [
                    event.token.span.start.line
                    for event in (key_event, colon_event, value_event)
                    if event.token is not None
                ]

                if len(set(line_array)) != 1:
                    raise self.error(
                        ErrorCode.UNEXPECTED_CONTENT,
                        "a flow mapping key, its ':' and the start of its value "
                        "must be on one line",
                        key_event,
                    )

                value = self.parse_flow_value(colon_event.index + 1, depth + 1)
                _add_unique_item(
                    mapping, key, value, key_token=key_event.token, source_name=self.source_name
                )
                event = self.advance()

                if event.kind is korml.lexer.v1.TokenType.FLOW_MAPPING_END:
                    break

                if event.kind is not korml.lexer.v1.TokenType.FLOW_SEPARATOR:
                    raise self.error(
                        ErrorCode.UNEXPECTED_CONTENT,
                        lambda what: f"unexpected {what}; expected ',' or '}}' in flow mapping",
                        event,
                    )

        mapping.cst = self.cst(start)
        return mapping


def _add_unique_item(
    mapping: korml.model.Mapping[korml.lexer.v1.Token],
    key: str,
    value: korml.model.Value[korml.lexer.v1.Token],
    *,
    key_token: korml.lexer.v1.Token | None,
    source_name: str,
) -> None:
    """
    Add an entry to a parsed mapping, raising a ParseError for a repeated key.

    Keys are compared as decoded strings, so a, 'a' and "a" are the same
    key. Keeping the last value silently would let two readers of the same
    file see different values for the same key.

    @param mapping The mapping being built.

    @param key The decoded key.

    @param value The value of the entry.

    @param key_token The key token, for the error.

    @param source_name The name of the source, for diagnostics.
    """
    if key in mapping:
        raise _make_parse_error(
            ErrorCode.DUPLICATE_KEY,
            message=f"duplicate mapping key {key!r}",
            source_name=source_name,
            at=key_token,
            unquoted_message="duplicate mapping key",
        )

    mapping.add_item(key, value)


def _parse_body(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
    depth: int,
    budget: _ParseBudget | None = None,
    max_depth: int | None = MAX_NESTING_DEPTH,
) -> korml.model.Value[korml.lexer.v1.Token] | None:
    """
    Parse the tokens of one document body; return None for an empty body.

    The root value keeps every token of the body as its CST, leading and
    trailing trivia included.

    @param token_array The concrete tokens of the document body.

    @param version The language version.

    @param source_name The name of the source, for diagnostics.

    @param depth The number of collections around the root.

    @param budget The work left, shared between the documents of a source.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The root value, or None for an empty body.
    """
    parser = _Parser(
        tuple(token_array),
        version=version,
        source_name=source_name,
        budget=budget,
        max_depth=max_depth,
    )
    return parser.parse_body(depth)


def _parse_value(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
    depth: int,
    budget: _ParseBudget | None = None,
    max_depth: int | None = MAX_NESTING_DEPTH,
) -> korml.model.Value[korml.lexer.v1.Token]:
    """
    Parse the tokens of a document body that must hold a root value.

    @param token_array The concrete tokens of the document body.

    @param version The language version.

    @param source_name The name of the source, for diagnostics.

    @param depth The number of collections around the root.

    @param budget The work left, shared between the documents of a source.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The root value.
    """
    value = _parse_body(
        token_array,
        version=version,
        source_name=source_name,
        depth=depth,
        budget=budget,
        max_depth=max_depth,
    )

    if value is None:
        raise _make_parse_error(
            ErrorCode.EXPECTED_VALUE,
            message="expected value",
            source_name=source_name,
            at=None,
        )

    return value


def _parse_sequence(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
    depth: int,
    budget: _ParseBudget | None = None,
    max_depth: int | None = MAX_NESTING_DEPTH,
) -> korml.model.Sequence[korml.lexer.v1.Token]:
    """
    Parse the tokens of a document body whose root must be a sequence.

    @param token_array The concrete tokens of the document body.

    @param version The language version.

    @param source_name The name of the source, for diagnostics.

    @param depth The number of collections around the root.

    @param budget The work left, shared between the documents of a source.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The root sequence.
    """
    value = _parse_value(
        token_array,
        version=version,
        source_name=source_name,
        depth=depth,
        budget=budget,
        max_depth=max_depth,
    )

    if not isinstance(value, korml.model.Sequence):
        raise _make_parse_error(
            ErrorCode.EXPECTED_SEQUENCE,
            message="expected sequence",
            source_name=source_name,
            at=_first_non_trivia(token_array),
        )

    return value


def _parse_mapping(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
    depth: int,
    budget: _ParseBudget | None = None,
    max_depth: int | None = MAX_NESTING_DEPTH,
) -> korml.model.Mapping[korml.lexer.v1.Token]:
    """
    Parse the tokens of a document body whose root must be a mapping.

    @param token_array The concrete tokens of the document body.

    @param version The language version.

    @param source_name The name of the source, for diagnostics.

    @param depth The number of collections around the root.

    @param budget The work left, shared between the documents of a source.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The root mapping.
    """
    value = _parse_value(
        token_array,
        version=version,
        source_name=source_name,
        depth=depth,
        budget=budget,
        max_depth=max_depth,
    )

    if not isinstance(value, korml.model.Mapping):
        raise _make_parse_error(
            ErrorCode.EXPECTED_MAPPING,
            message="expected mapping",
            source_name=source_name,
            at=_first_non_trivia(token_array),
        )

    return value
