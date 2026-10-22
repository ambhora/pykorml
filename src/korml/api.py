# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc
import copy
import pathlib
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
) -> korml.model.Stream[korml.lexer.v1.Token]:
    korml._limits.check_input_size(input_text, max_input_bytes=max_input_bytes, filename=filename)
    # A byte-order mark is an artefact of the encoding, not Korml text; it is
    # dropped as YAML does, so a file saved with one reads like one without.
    file = korml.lexer.file.lex(
        filename=filename,
        input_text=input_text.removeprefix("\ufeff"),
        debug=debug,
        max_tokens=max_tokens,
    )

    if file.version is korml.model.Version.v0:
        return korml.parser.v0.parse(file, max_tokens=max_tokens, max_work=max_parse_work)

    if file.version is korml.model.Version.v1:
        return korml.parser.v1.parse(file, max_tokens=max_tokens, max_work=max_parse_work)

    raise ValueError(f"unsupported korml version: {file.version.value!r}")


def load(
    filename: str | pathlib.Path,
    *,
    debug: bool = False,
    max_input_bytes: int | None = korml._limits.MAX_INPUT_BYTES,
    max_tokens: int | None = korml._limits.MAX_TOKENS,
    max_parse_work: int | None = korml._limits.MAX_PARSE_WORK,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    path = pathlib.Path(filename)
    with path.open("rb") as stream:
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
    )


def dumps(
    value: object,
    *,
    version: korml.model.Version = korml.model.Version.v1,
) -> str:
    if version is korml.model.Version.v0:
        return korml.emitter.v0.emit(_make_stream(value, version=version))

    if version is korml.model.Version.v1:
        return korml.emitter.v1.emit(_make_stream(value, version=version))

    raise ValueError(f"unsupported korml version: {version.value!r}")


def dump(
    value: object,
    filename: str | pathlib.Path,
    *,
    version: korml.model.Version = korml.model.Version.v1,
    dangerous_allow_writing_to_symlink: bool = False,
) -> None:
    """
    Write value as Korml to the file filename, replacing it atomically.

    A symbolic link at filename is refused with UnsafeOutputError unless
    dangerous_allow_writing_to_symlink is true; then the file it points to
    is replaced and the link is kept.
    """
    korml._atomic.write_bytes(
        filename,
        dumps(value, version=version).encode("utf-8"),
        dangerous_allow_writing_to_symlink=dangerous_allow_writing_to_symlink,
    )


def _make_stream(
    value: object,
    *,
    version: korml.model.Version,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    if isinstance(value, korml.model.Stream):
        return value

    if isinstance(value, korml.model.Value):
        return korml.model.Stream[korml.lexer.v1.Token](
            document_array=[value],
            cst=korml.model.CST(version=version),
        )

    return korml.model.Stream[korml.lexer.v1.Token](
        document_array=[_make_value(value, version=version)],
        cst=korml.model.CST(version=version),
    )


def _make_value(
    value: object,
    *,
    version: korml.model.Version,
) -> korml.model.Value[korml.lexer.v1.Token]:
    if isinstance(value, str):
        return korml.model.Scalar[korml.lexer.v1.Token](
            value,
            cst=korml.model.CST(version=version),
        )

    if isinstance(value, list):
        return korml.model.Sequence[korml.lexer.v1.Token](
            value_array=[_make_value(child, version=version) for child in value],
            cst=korml.model.CST(version=version),
        )

    if isinstance(value, dict):
        mapping = korml.model.Mapping[korml.lexer.v1.Token](
            cst=korml.model.CST(version=version),
        )

        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings")

            mapping.add_item(key, _make_value(child, version=version))

        return mapping

    raise TypeError(f"cannot dump {type(value).__name__!r}")


_TRIVIA_SET = {
    korml.lexer.v1.TokenType.WHITESPACE,
    korml.lexer.v1.TokenType.COMMENT,
    korml.lexer.v1.TokenType.NEWLINE,
}

_BLOCK_SCALAR_SET = {
    korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR,
    korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR,
}


def edit(
    *,
    stream: korml.model.Stream[korml.lexer.v1.Token],
    replacements: collections.abc.Sequence[tuple[korml.model.Value[korml.lexer.v1.Token], str]],
) -> str:
    """
    Return the source of a parsed stream with some values replaced by strings.

    Each replacement pairs a value of the stream, as returned by loads or
    load, with the string it becomes. Only the tokens of the replaced values
    change; every comment, blank line, indentation and quoting style
    elsewhere is kept, so a tool can change a value without reformatting the
    file. A replaced value can be a scalar or a whole collection; the string
    is always written as a double-quoted scalar, and a replaced block
    collection becomes a scalar on the line of its key or dash.

    The result is parsed again and must equal the original with the
    replacements applied; anything else is a BugError, so an edit can never
    change more than it says.
    """
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

        splice_array.append(_splice_for(value, text, index_map=index_map))
        path_array.append((path, text))

    splice_array.sort()
    for (_, previous_end, _), (start, _, _) in zip(splice_array, splice_array[1:], strict=False):
        if start < previous_end:
            raise ValueError("replacement values overlap")

    expected = copy.deepcopy(stream.to_builtin())
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
    )
    if reread.to_builtin() != expected:
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
) -> tuple[int, int, str]:
    """Return the token range a replaced value covers and the text it becomes."""
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
    # replacing it goes on that line, after one space.
    block_collection = (
        isinstance(value, (korml.model.Mapping, korml.model.Sequence))
        and value.style is korml.model.Style.block
    )
    if block_collection and value.token_array:
        return index_map[id(value.token_array[0])], end, " " + scalar

    return start, end, scalar


def _final_line_break(value: str) -> str:
    for line_break in ("\r\n", "\n", "\r"):
        if value.endswith(line_break):
            return line_break
    return ""


def _value_path_map(
    stream: korml.model.Stream[korml.lexer.v1.Token],
) -> dict[int, tuple[int | str, ...]]:
    """Map the identity of every value of a stream to its path."""
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
    container: typing.Any = builtin
    for part in path[:-1]:
        container = container[part]
    container[path[-1]] = text
