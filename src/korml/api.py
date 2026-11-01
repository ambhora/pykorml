# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc
import os
import pathlib
import stat
import typing

import korml._atomic
import korml._limits
import korml.emitter.v0
import korml.emitter.v1
import korml.error
import korml.lexer.file
import korml.lexer.v1
import korml.model
import korml.parser.v0
import korml.parser.v1

__all__ = ["dump", "dumps", "edit", "load", "loads"]


def loads(
    input_text: str,
    *,
    filename: str = "<string>",
    debug: bool = False,
    max_input_bytes: int | None = korml._limits.MAX_INPUT_BYTES,
    max_tokens: int | None = korml._limits.MAX_TOKENS,
    max_parse_work: int | None = korml._limits.MAX_PARSE_WORK,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    """
    Parse Korml source text into a stream of documents.

    The limits guard against hostile input; None removes one. max_input_bytes
    bounds the size of the text, max_tokens the number of tokens,
    max_parse_work the parser's work, and max_depth the nesting of
    collections (deeper is a ParseError with the code TOO_DEEP; with None,
    nesting too deep for Python's recursion limit raises the same error).
    An empty document is an Empty in the stream.

    @param input_text The Korml source text.

    @param filename The name of the source, for diagnostics.

    @param debug Whether to trace the lexer on standard error.

    @param max_input_bytes The largest source accepted, in bytes, or None for no limit.

    @param max_tokens The largest number of tokens accepted, or None for no limit.

    @param max_parse_work The largest amount of parser work accepted, or None for no limit.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The stream of documents, an Empty for each document without content.
    """
    korml._limits.check_max_depth(max_depth)
    korml._limits.check_input_size(input_text, max_input_bytes=max_input_bytes, filename=filename)
    # A byte-order mark is not allowed anywhere in a korml source, not even
    # at the start: the lexer rejects it rather than dropping it, so every
    # reader sees the same text.
    file = korml.lexer.file.lex(
        filename=filename,
        input_text=input_text,
        debug=debug,
        max_tokens=max_tokens,
    )

    if file.version is korml.model.Version.v0:
        return korml.parser.v0.parse(
            file, max_tokens=max_tokens, max_work=max_parse_work, max_depth=max_depth
        )

    if file.version is korml.model.Version.v1:
        return korml.parser.v1.parse(
            file, max_tokens=max_tokens, max_work=max_parse_work, max_depth=max_depth
        )

    raise ValueError(f"unsupported korml version: {file.version.value!r}")


def load(
    filename: str | pathlib.Path,
    *,
    debug: bool = False,
    max_input_bytes: int | None = korml._limits.MAX_INPUT_BYTES,
    max_tokens: int | None = korml._limits.MAX_TOKENS,
    max_parse_work: int | None = korml._limits.MAX_PARSE_WORK,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    """
    Read and parse the Korml file filename.

    The limits are those of loads, max_depth included.

    Only a regular file is read. A FIFO, a device or a directory is refused
    with a CompilerError: reading a FIFO waits for a writer forever, and a
    device such as /dev/zero never ends. The file is opened without
    blocking and checked after opening, so it cannot be swapped for a FIFO
    between the check and the read.

    @param filename The path of the file.

    @param debug Whether to trace the lexer on standard error.

    @param max_input_bytes The largest source accepted, in bytes, or None for no limit.

    @param max_tokens The largest number of tokens accepted, or None for no limit.

    @param max_parse_work The largest amount of parser work accepted, or None for no limit.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The stream of documents, an Empty for each document without content.
    """
    korml._limits.check_max_depth(max_depth)
    path = pathlib.Path(filename)
    with _open_regular_file(path) as stream:
        data = stream.read(max_input_bytes + 1 if max_input_bytes is not None else -1)
    if max_input_bytes is not None and len(data) > max_input_bytes:
        raise korml.error.CompilerError(
            message=f"input exceeds {max_input_bytes} bytes",
            source_name=str(path),
            code="INPUT_TOO_LARGE",
        )
    try:
        input_text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise korml.error.CompilerError(
            message=f"input is not valid UTF-8 at byte {error.start}",
            source_name=str(path),
            code="INVALID_ENCODING",
        ) from error

    return loads(
        input_text,
        filename=str(path),
        debug=debug,
        max_input_bytes=max_input_bytes,
        max_tokens=max_tokens,
        max_parse_work=max_parse_work,
        max_depth=max_depth,
    )


def _open_regular_file(path: pathlib.Path) -> typing.BinaryIO:
    """
    Open path for reading without blocking, refusing anything but a regular file.

    @param path The path of the file.

    @return The file, open for reading bytes.
    """
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))

    try:
        is_regular_file = stat.S_ISREG(os.fstat(descriptor).st_mode)
    except BaseException:
        os.close(descriptor)
        raise

    if not is_regular_file:
        os.close(descriptor)
        raise korml.error.CompilerError(
            message="input is not a regular file",
            source_name=str(path),
            code="NOT_A_REGULAR_FILE",
        )

    return os.fdopen(descriptor, "rb")


def dumps(
    value: object,
    *,
    version: korml.model.Version = korml.model.Version.v1,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> str:
    """
    Return value as Korml source.

    value is a stream, a korml value, or plain Python data: str, list and
    dict with string keys, or None at the top, which is an empty document.

    max_depth is the deepest nesting of collections written; deeper nesting,
    or a container that contains itself, is an EmitError. With None there
    is no korml limit, and nesting too deep for Python's recursion limit is
    an EmitError with the code TOO_DEEP.

    @param value A stream, a korml value, or plain Python data.

    @param version The language version to write.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The Korml source.
    """
    korml._limits.check_max_depth(max_depth)

    if version is korml.model.Version.v0:
        emit = korml.emitter.v0.emit
    elif version is korml.model.Version.v1:
        emit = korml.emitter.v1.emit
    else:
        raise ValueError(f"unsupported korml version: {version.value!r}")

    try:
        return emit(_make_stream(value, version=version, max_depth=max_depth), max_depth=max_depth)
    except RecursionError as error:
        raise korml.error.EmitError(
            message=korml._limits.too_deep_message(max_depth),
            code=str(korml.emitter.v1.ErrorCode.TOO_DEEP),
        ) from error


def dump(
    value: object,
    filename: str | pathlib.Path,
    *,
    version: korml.model.Version = korml.model.Version.v1,
    dangerous_allow_writing_to_symlink: bool = False,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> None:
    """
    Write value as Korml to the file filename, replacing it atomically.

    value and max_depth are as for dumps.

    A symbolic link at filename is refused with UnsafeOutputError unless
    dangerous_allow_writing_to_symlink is true; then the file it points to
    is replaced and the link is kept.

    @param value A stream, a korml value, or plain Python data.

    @param filename The path of the output file.

    @param version The language version to write.

    @param dangerous_allow_writing_to_symlink Whether to replace the file a symbolic link at the
        path points to, rather than refuse.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.
    """
    korml._atomic.write_bytes(
        filename,
        dumps(value, version=version, max_depth=max_depth).encode("utf-8"),
        dangerous_allow_writing_to_symlink=dangerous_allow_writing_to_symlink,
    )


def _make_stream(
    value: object,
    *,
    version: korml.model.Version,
    max_depth: int | None,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    """
    Return value as a stream, whichever form dumps received it in.

    @param value A stream, a korml value, or plain Python data.

    @param version The language version of a new stream.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The stream to emit.
    """
    if isinstance(value, korml.model.Stream):
        return value

    if isinstance(value, korml.model.Value):
        return korml.model.Stream[korml.lexer.v1.Token](
            document_array=[value],
            cst=korml.model.CST(version=version),
        )

    # None is what to_builtin gives for an empty document, so it dumps as
    # one; inside a collection it is refused like any other non-string.
    if value is None:
        document: korml.model.Value[korml.lexer.v1.Token] = korml.model.Empty(
            cst=korml.model.CST(version=version)
        )
    else:
        document = _make_value(
            value, version=version, depth=0, max_depth=max_depth, active_id_set=set()
        )

    return korml.model.Stream[korml.lexer.v1.Token](
        document_array=[document],
        cst=korml.model.CST(version=version),
    )


def _make_value(
    value: object,
    *,
    version: korml.model.Version,
    depth: int,
    max_depth: int | None,
    active_id_set: set[int],
) -> korml.model.Value[korml.lexer.v1.Token]:
    """
    Convert a plain Python value into a korml value.

    The conversion recurses once per level of nesting, so it refuses
    containers nested deeper than max_depth and a container that contains
    itself, with an EmitError instead of a RecursionError. active_id_set
    holds the containers on the current path; a container shared by two
    branches is not a cycle and is written twice.

    @param value The plain Python value.

    @param version The language version of the new value.

    @param depth The number of collections around this value.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param active_id_set The identities of the containers on the path to this value.

    @return The korml value.
    """
    if isinstance(value, str):
        return korml.model.Scalar[korml.lexer.v1.Token](
            value,
            cst=korml.model.CST(version=version),
        )

    if not isinstance(value, (list, dict)):
        raise TypeError(f"cannot dump {type(value).__name__!r}")

    if korml._limits.is_too_deep(depth, max_depth):
        raise korml.error.EmitError(
            message=korml._limits.too_deep_message(max_depth),
            code=str(korml.emitter.v1.ErrorCode.TOO_DEEP),
        )

    if id(value) in active_id_set:
        raise korml.error.EmitError(
            message=f"cannot dump a {type(value).__name__} that contains itself",
            code=str(korml.emitter.v1.ErrorCode.UNSUPPORTED_VALUE),
        )

    active_id_set.add(id(value))

    try:
        if isinstance(value, list):
            return korml.model.Sequence[korml.lexer.v1.Token](
                value_array=[
                    _make_value(
                        child,
                        version=version,
                        depth=depth + 1,
                        max_depth=max_depth,
                        active_id_set=active_id_set,
                    )
                    for child in value
                ],
                cst=korml.model.CST(version=version),
            )

        mapping = korml.model.Mapping[korml.lexer.v1.Token](
            cst=korml.model.CST(version=version),
        )

        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings")

            mapping.add_item(
                key,
                _make_value(
                    child,
                    version=version,
                    depth=depth + 1,
                    max_depth=max_depth,
                    active_id_set=active_id_set,
                ),
            )

        return mapping
    finally:
        active_id_set.discard(id(value))


_TRIVIA_SET = {
    korml.lexer.v1.TokenType.WHITESPACE,
    korml.lexer.v1.TokenType.COMMENT,
    korml.lexer.v1.TokenType.NEWLINE,
}

_NEWLINE = korml.lexer.v1.TokenType.NEWLINE

_BLOCK_SCALAR_SET = {
    korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
    korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
}


def edit(
    *,
    stream: korml.model.Stream[korml.lexer.v1.Token],
    replacements: collections.abc.Sequence[tuple[korml.model.Value[korml.lexer.v1.Token], str]],
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> str:
    """
    Return the source of a parsed stream with some values replaced by strings.

    Each replacement pairs a value of the stream, as returned by loads or
    load, with the string it becomes. Only the tokens of the replaced values
    change; every comment, blank line, indentation and quoting style
    elsewhere is kept, so a tool can change a value without reformatting the
    file. A replaced value can be a scalar or a whole collection; the string
    is always written as a double-quoted scalar, and a replaced block
    collection becomes a scalar on the line of its key or dash. Replacing an
    empty document (an Empty) gives it a root scalar on the line after its
    '---', or on the first line of a v0 source.

    max_depth limits the nesting of the stream and of the edited source, as
    for loads; pass the max_depth the stream was loaded with.

    The result is parsed again and must equal the original with the
    replacements applied; anything else is a BugError, so an edit can never
    change more than it says. That check parses without the default resource
    limits: the stream was already accepted under its caller's limits when
    it was loaded, and the edited source differs from it only by the
    replacement strings, each a single double-quoted scalar, so it nests no
    deeper and has at most a few tokens more per replacement. The work is
    bounded by the size of the stream and the replacements the caller
    passes, not by anything an untrusted source can choose.

    @param stream The stream as loaded, whose tokens give the source.

    @param replacements Pairs of a value of the stream and the string it becomes.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The edited source.
    """
    korml._limits.check_max_depth(max_depth)
    token_array = stream.token_array
    index_map = {id(token): index for index, token in enumerate(token_array)}
    path_map = _value_path_map(stream)
    splice_array: list[tuple[int, int, str]] = []
    path_array: list[tuple[tuple[int | str, ...], str]] = []

    for value, text in replacements:
        if not isinstance(text, str):
            raise TypeError("replacement text must be a string")

        path = path_map.get(id(value))
        if path is None:
            raise ValueError("replacement value is not a value of this stream")

        if isinstance(value, korml.model.Empty):
            splice_array.append(_splice_for_empty(value, text, stream=stream, index_map=index_map))
        else:
            splice_array.append(
                _splice_for(value, text, index_map=index_map, is_root=len(path) == 1)
            )
        path_array.append((path, text))

    splice_array.sort()
    # Equal starts catch an empty document replaced twice: its splice covers
    # no tokens, so it cannot overlap anything by range.
    for (previous_start, previous_end, _), (start, _, _) in zip(
        splice_array, splice_array[1:], strict=False
    ):
        if start < previous_end or start == previous_start:
            raise ValueError("replacement values overlap")

    # to_builtin builds new containers, so expected can be changed freely.
    expected = stream.to_builtin(max_depth=max_depth)
    for path, text in path_array:
        _set_path(expected, path, text)

    piece_array: list[str] = []
    cursor = 0
    for start, end, text in splice_array:
        piece_array.extend(token.value for token in token_array[cursor:start])
        piece_array.append(text)
        cursor = end
    piece_array.extend(token.value for token in token_array[cursor:])
    source = "".join(piece_array)

    # The stream was accepted under its caller's limits when it was loaded,
    # so the check reads the edited source without limits; with the default
    # limits, a stream loaded with larger ones could never be edited.
    reread = loads(
        source,
        filename=stream.filename,
        max_input_bytes=None,
        max_tokens=None,
        max_parse_work=None,
        max_depth=max_depth,
    )
    if reread.to_builtin(max_depth=max_depth) != expected:
        raise korml.error.BugError(
            message="edited source does not read back as the edited values",
            location="korml.api.edit",
            source_name=stream.filename,
        )

    return source


def _splice_for(
    value: korml.model.Value[korml.lexer.v1.Token],
    text: str,
    *,
    index_map: dict[int, int],
    is_root: bool,
) -> tuple[int, int, str]:
    """
    Return the token range a replaced value covers and the text it becomes.

    @param value The value being replaced.

    @param text The string it becomes.

    @param index_map The position in the stream of each token, by identity.

    @param is_root Whether the value is the root of its document.

    @return The first token index, the index after the last, and the replacing text.
    """
    content_array = [token for token in value.token_array if token.type not in _TRIVIA_SET]
    if not content_array:
        raise ValueError("replacement value has no tokens")

    start = index_map[id(content_array[0])]
    end = index_map[id(content_array[-1])] + 1
    scalar = korml.emitter.v1._format_double_quoted_scalar(text)

    # A block scalar token includes the line break that ends its last line;
    # the quoted scalar replacing it keeps that line break.
    if content_array[-1].type in _BLOCK_SCALAR_SET:
        scalar += _final_line_break(content_array[-1].value)

    # A block collection starts on the line after its key or dash; the scalar
    # replacing it goes on that line, after one space. A root collection has
    # no key or dash, and its replacement starts at column 1 where it did.
    block_collection = (
        isinstance(value, (korml.model.Mapping, korml.model.Sequence))
        and value.style is korml.model.Style.block
    )
    if block_collection and value.token_array and not is_root:
        return index_map[id(value.token_array[0])], end, " " + scalar

    return start, end, scalar


def _splice_for_empty(
    value: korml.model.Empty[korml.lexer.v1.Token],
    text: str,
    *,
    stream: korml.model.Stream[korml.lexer.v1.Token],
    index_map: dict[int, int],
) -> tuple[int, int, str]:
    """
    Return where the root scalar replacing an empty document goes.

    In v1 that is the start of the line after '---', whose line break the
    body starts with; in v0 it is the start of the source. The scalar gets
    its own line, ended with the line break the source uses.

    @param value The empty document being replaced.

    @param text The string it becomes.

    @param stream The stream that holds the document.

    @param index_map The position in the stream of each token, by identity.

    @return The token index to insert at, twice, and the text to insert.
    """
    line_break = next(
        (token.value for token in stream.token_array if token.type is _NEWLINE),
        "\n",
    )
    scalar = korml.emitter.v1._format_double_quoted_scalar(text) + line_break

    if stream.version is korml.model.Version.v0:
        return 0, 0, scalar

    for token in value.token_array:
        if token.type is _NEWLINE:
            index = index_map[id(token)] + 1
            return index, index, scalar

    raise ValueError("empty document has no line after its start marker")


def _final_line_break(value: str) -> str:
    """
    Return the line break that ends value.

    @param value The source text of a token.

    @return The line break, or an empty string if there is none.
    """
    for line_break in ("\r\n", "\n", "\r"):
        if value.endswith(line_break):
            return line_break
    return ""


def _value_path_map(
    stream: korml.model.Stream[korml.lexer.v1.Token],
) -> dict[int, tuple[int | str, ...]]:
    """
    Map the identity of every value of a stream to its path.

    @param stream The stream to walk.

    @return The path of each value, by identity: the document index, then keys and sequence indices.
    """
    path_map: dict[int, tuple[int | str, ...]] = {}
    pending: list[tuple[korml.model.Value[korml.lexer.v1.Token], tuple[int | str, ...]]] = [
        (document, (index,)) for index, document in enumerate(stream.document_array)
    ]
    while pending:
        value, path = pending.pop()
        path_map[id(value)] = path
        if isinstance(value, korml.model.Mapping):
            pending.extend((child, (*path, key)) for key, child in value.value_map.items())
        elif isinstance(value, korml.model.Sequence):
            pending.extend((child, (*path, index)) for index, child in enumerate(value))
    return path_map


def _set_path(builtin: list[object], path: tuple[int | str, ...], text: str) -> None:
    """
    Replace the value at path in plain data with text.

    @param builtin The plain data of the stream, one item per document.

    @param path The path of the value, as from _value_path_map.

    @param text The string it becomes.
    """
    container: typing.Any = builtin
    for part in path[:-1]:
        container = container[part]
    container[path[-1]] = text
