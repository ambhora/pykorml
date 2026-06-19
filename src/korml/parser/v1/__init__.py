# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc
import enum

import korml.error
import korml.lexer.v1
import korml.model

__all__ = ["ErrorCode", "parse"]


class ErrorCode(str, enum.Enum):
    EXPECTED_VALUE = "EXPECTED_VALUE"
    EXPECTED_SCALAR = "EXPECTED_SCALAR"
    EXPECTED_SEQUENCE = "EXPECTED_SEQUENCE"
    EXPECTED_MAPPING = "EXPECTED_MAPPING"
    EXPECTED_MAPPING_COLON = "EXPECTED_MAPPING_COLON"

    def __str__(self) -> str:
        return self.value


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

_DOUBLE_QUOTED_ESCAPE_MAP = {
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "\t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    '"': '"',
    "\\": "\\",
    "/": "/",
}


def parse(
    file: korml.lexer.v1.File,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    if file.version is not korml.model.Version.v1:
        raise ValueError(f"parser v1 cannot parse version {file.version.value!r}")

    document_array: list[korml.model.Value[korml.lexer.v1.Token]] = []

    for document_token_array in _iter_document_body_token_arrays(file.token_array):
        if _first_non_trivia(document_token_array) is None:
            continue

        document_array.append(
            _parse_value(
                document_token_array,
                version=file.version,
                source_name=file.filename,
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


def _iter_document_body_token_arrays(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> collections.abc.Iterator[tuple[korml.lexer.v1.Token, ...]]:
    in_document = False
    start = 0

    for index, token in enumerate(token_array):
        if token.type is korml.lexer.v1.TokenType.DOC_START:
            in_document = True
            start = index + 1
            continue

        if token.type is korml.lexer.v1.TokenType.DOC_END and in_document:
            yield tuple(token_array[start:index])
            in_document = False

    if in_document:
        yield tuple(token_array[start:])


def _parse_scalar(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Scalar[korml.lexer.v1.Token]:
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

    return korml.model.Scalar[korml.lexer.v1.Token](
        _parse_scalar_token_value(token),
        cst=korml.model.CST(
            version=version,
            token_array=concrete_token_array,
        ),
    )


def _without_trivia(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> tuple[korml.lexer.v1.Token, ...]:
    return tuple(token for token in token_array if token.type not in _TRIVIA_TOKEN_TYPE_SET)


def _parse_scalar_token_value(token: korml.lexer.v1.Token) -> str:
    match token.type:
        case korml.lexer.v1.TokenType.PLAIN_SCALAR:
            return token.value

        case korml.lexer.v1.TokenType.SQ_SCALAR:
            return _parse_single_quoted_scalar_value(token.value)

        case korml.lexer.v1.TokenType.DQ_SCALAR:
            return _parse_double_quoted_scalar_value(token.value)

        case korml.lexer.v1.TokenType.LITERAL_BLOCK_SCALAR:
            return _parse_literal_block_scalar_value(token.value)

        case korml.lexer.v1.TokenType.FOLDED_BLOCK_SCALAR:
            return _parse_folded_block_scalar_value(token.value)

        case _:
            raise korml.error.BugError(
                message="unsupported scalar token type",
                location="korml.parser.v1._parse_scalar_token_value",
                details=f"token type is {token.type!r}",
                span=token.span,
            )


def _parse_single_quoted_scalar_value(source: str) -> str:
    return source[1:-1].replace("''", "'")


def _parse_double_quoted_scalar_value(source: str) -> str:
    content = source[1:-1]
    output: list[str] = []
    index = 0

    while index < len(content):
        char = content[index]

        if char != "\\":
            output.append(char)
            index += 1
            continue

        index += 1

        if index >= len(content):
            output.append("\\")
            break

        escaped_char = content[index]
        output.append(_DOUBLE_QUOTED_ESCAPE_MAP.get(escaped_char, escaped_char))
        index += 1

    return "".join(output)


def _parse_literal_block_scalar_value(source: str) -> str:
    return _clip_block_scalar_text(_dedent_block_scalar_content(_block_scalar_content(source)))


def _parse_folded_block_scalar_value(source: str) -> str:
    content = _dedent_block_scalar_content(_block_scalar_content(source))

    return _fold_block_scalar_content(content)


def _block_scalar_content(source: str) -> str:
    header_end = _find_first_line_end(source)

    if header_end >= len(source):
        return ""

    return source[header_end:]


def _find_first_line_end(source: str) -> int:
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


def _dedent_block_scalar_content(source: str) -> str:
    line_array = source.splitlines(keepends=True)
    indent = _detect_block_scalar_indent(line_array)

    if indent == 0:
        return source

    return "".join(_remove_indent(line, indent) for line in line_array)


def _detect_block_scalar_indent(line_array: collections.abc.Sequence[str]) -> int:
    indent_array: list[int] = []

    for line in line_array:
        content = line.rstrip("\r\n")

        if content.strip() == "":
            continue

        indent_array.append(len(content) - len(content.lstrip(" ")))

    if not indent_array:
        return 0

    return min(indent_array)


def _remove_indent(line: str, indent: int) -> str:
    removed = 0
    index = 0

    while removed < indent and index < len(line) and line[index] == " ":
        index += 1
        removed += 1

    return line[index:]


def _clip_block_scalar_text(source: str) -> str:
    if source == "":
        return ""

    return source.rstrip("\n") + "\n"


def _fold_block_scalar_content(source: str) -> str:
    paragraph_array: list[str] = []
    current_line_array: list[str] = []

    for line in source.splitlines():
        text = line.strip()

        if text == "":
            if current_line_array:
                paragraph_array.append(" ".join(current_line_array))
                current_line_array = []
            continue

        current_line_array.append(text)

    if current_line_array:
        paragraph_array.append(" ".join(current_line_array))

    if not paragraph_array:
        return ""

    return _clip_block_scalar_text("\n".join(paragraph_array))


def _make_expected_scalar_error(
    *,
    source_name: str,
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> korml.error.ParseError:
    return _make_parse_error(
        ErrorCode.EXPECTED_SCALAR,
        message="expected scalar",
        source_name=source_name,
    )


def _make_parse_error(
    code: ErrorCode,
    *,
    message: str,
    source_name: str,
) -> korml.error.ParseError:
    return korml.error.ParseError(
        message=message,
        source_name=source_name,
        code=str(code),
    )


def _find_block_sequence_item_start_array(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    indent: int,
) -> list[int]:
    return [
        index
        for index, token in enumerate(token_array)
        if token.type is korml.lexer.v1.TokenType.DASH_ITEM
        and token.span.start.column == indent
        and _is_first_content_token_on_line(token_array, index)
    ]


def _find_block_sequence_item_end(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    item_start_array: collections.abc.Sequence[int],
    item_index: int,
    indent: int,
) -> int:
    dash_index = item_start_array[item_index]

    if item_index + 1 < len(item_start_array):
        limit = item_start_array[item_index + 1]
    else:
        limit = len(token_array)

    index = dash_index + 1

    while index < limit:
        token = token_array[index]

        if token.type in _TRIVIA_TOKEN_TYPE_SET:
            index += 1
            continue

        if _is_first_content_token_on_line(token_array, index) and token.span.start.column <= indent:
            return index

        index += 1

    return limit


def _find_block_mapping_entry_start_array(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    indent: int,
) -> list[int]:
    entry_start_array: list[int] = []

    for index, token in enumerate(token_array):
        if token.type not in _SCALAR_TOKEN_TYPE_SET:
            continue

        if token.span.start.column != indent:
            continue

        if not _is_first_content_token_on_line(token_array, index):
            continue

        colon_index = _next_non_trivia_index(token_array, index + 1)

        if colon_index is not None and token_array[colon_index].type is korml.lexer.v1.TokenType.COLON:
            entry_start_array.append(index)

    return entry_start_array


def _find_block_mapping_entry_end(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    entry_start_array: collections.abc.Sequence[int],
    entry_index: int,
    indent: int,
) -> int:
    key_index = entry_start_array[entry_index]

    if entry_index + 1 < len(entry_start_array):
        limit = entry_start_array[entry_index + 1]
    else:
        limit = len(token_array)

    index = key_index + 1

    while index < limit:
        token = token_array[index]

        if token.type in _TRIVIA_TOKEN_TYPE_SET:
            index += 1
            continue

        if _is_first_content_token_on_line(token_array, index) and token.span.start.column < indent:
            return index

        index += 1

    return limit


def _is_first_content_token_on_line(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    index: int,
) -> bool:
    token = token_array[index]
    cursor = index - 1

    while cursor >= 0:
        previous_token = token_array[cursor]

        if previous_token.type is korml.lexer.v1.TokenType.NEWLINE:
            return True

        if previous_token.type in _TRIVIA_TOKEN_TYPE_SET:
            cursor -= 1
            continue

        if previous_token.span.end.line < token.span.start.line:
            return True

        if (
            previous_token.span.end.line == token.span.start.line
            and previous_token.span.end.offset <= token.span.start.offset
            and _ends_with_line_break(previous_token.value)
        ):
            return True

        return False

    return True


def _ends_with_line_break(value: str) -> bool:
    return value.endswith("\n") or value.endswith("\r")


def _find_mapping_colon_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    key_index: int,
    end: int,
    source_name: str,
) -> int:
    colon_index = _next_non_trivia_index(token_array, key_index + 1, end=end)

    if colon_index is None or token_array[colon_index].type is not korml.lexer.v1.TokenType.COLON:
        raise _make_parse_error(
            ErrorCode.EXPECTED_MAPPING_COLON,
            message="expected ':' after mapping key",
            source_name=source_name,
        )

    return colon_index


def _looks_like_block_mapping(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> bool:
    first_index = _first_non_trivia_index(token_array)

    if first_index is None:
        return False

    first_token = token_array[first_index]

    if first_token.type not in _SCALAR_TOKEN_TYPE_SET:
        return False

    colon_index = _next_non_trivia_index(token_array, first_index + 1)

    return colon_index is not None and token_array[colon_index].type is korml.lexer.v1.TokenType.COLON


def _first_non_trivia(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> korml.lexer.v1.Token | None:
    index = _first_non_trivia_index(token_array)

    if index is None:
        return None

    return token_array[index]


def _first_non_trivia_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> int | None:
    return _next_non_trivia_index(token_array, 0)


def _next_non_trivia_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    start: int,
    *,
    end: int | None = None,
) -> int | None:
    if end is None:
        end = len(token_array)

    index = start

    while index < end:
        if token_array[index].type not in _TRIVIA_TOKEN_TYPE_SET:
            return index

        index += 1

    return None


def _parse_value(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Value[korml.lexer.v1.Token]:
    concrete_token_array = tuple(token_array)
    first_token = _first_non_trivia(concrete_token_array)

    if first_token is None:
        raise _make_parse_error(
            ErrorCode.EXPECTED_VALUE,
            message="expected value",
            source_name=source_name,
        )

    if first_token.type is korml.lexer.v1.TokenType.FLOW_SEQUENCE_START:
        return _parse_flow_sequence(
            concrete_token_array,
            version=version,
            source_name=source_name,
        )

    if first_token.type is korml.lexer.v1.TokenType.FLOW_MAPPING_START:
        return _parse_flow_mapping(
            concrete_token_array,
            version=version,
            source_name=source_name,
        )

    if first_token.type is korml.lexer.v1.TokenType.DASH_ITEM:
        return _parse_sequence(
            concrete_token_array,
            version=version,
            source_name=source_name,
        )

    if first_token.type in _SCALAR_TOKEN_TYPE_SET:
        if _looks_like_block_mapping(concrete_token_array):
            return _parse_mapping(
                concrete_token_array,
                version=version,
                source_name=source_name,
            )

        return _parse_scalar(
            concrete_token_array,
            version=version,
            source_name=source_name,
        )

    raise _make_parse_error(
        ErrorCode.EXPECTED_VALUE,
        message="expected value",
        source_name=source_name,
    )


def _parse_flow_sequence(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Sequence[korml.lexer.v1.Token]:
    concrete_token_array = tuple(token_array)
    start_index = _first_non_trivia_index(concrete_token_array)

    if (
        start_index is None
        or concrete_token_array[start_index].type is not korml.lexer.v1.TokenType.FLOW_SEQUENCE_START
    ):
        raise _make_parse_error(
            ErrorCode.EXPECTED_SEQUENCE,
            message="expected flow sequence",
            source_name=source_name,
        )

    end_index = _find_matching_flow_end(
        concrete_token_array,
        start_index=start_index,
        start_type=korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
        end_type=korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
        source_name=source_name,
    )

    element_array = _split_flow_item_token_arrays(
        concrete_token_array[start_index + 1 : end_index],
    )

    value_array = [
        _parse_value(
            element_token_array,
            version=version,
            source_name=source_name,
        )
        for element_token_array in element_array
        if _first_non_trivia(element_token_array) is not None
    ]

    return korml.model.Sequence[korml.lexer.v1.Token](
        value_array=value_array,
        style=korml.model.Style.flow,
        cst=korml.model.CST(
            version=version,
            token_array=concrete_token_array,
        ),
    )


def _parse_flow_mapping(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Mapping[korml.lexer.v1.Token]:
    concrete_token_array = tuple(token_array)
    start_index = _first_non_trivia_index(concrete_token_array)

    if (
        start_index is None
        or concrete_token_array[start_index].type is not korml.lexer.v1.TokenType.FLOW_MAPPING_START
    ):
        raise _make_parse_error(
            ErrorCode.EXPECTED_MAPPING,
            message="expected flow mapping",
            source_name=source_name,
        )

    end_index = _find_matching_flow_end(
        concrete_token_array,
        start_index=start_index,
        start_type=korml.lexer.v1.TokenType.FLOW_MAPPING_START,
        end_type=korml.lexer.v1.TokenType.FLOW_MAPPING_END,
        source_name=source_name,
    )

    mapping = korml.model.Mapping[korml.lexer.v1.Token](
        style=korml.model.Style.flow,
        cst=korml.model.CST(
            version=version,
            token_array=concrete_token_array,
        ),
    )

    for entry_token_array in _split_flow_item_token_arrays(
        concrete_token_array[start_index + 1 : end_index],
    ):
        if _first_non_trivia(entry_token_array) is None:
            continue

        colon_index = _find_top_level_flow_colon_index(entry_token_array)

        if colon_index is None:
            raise _make_parse_error(
                ErrorCode.EXPECTED_MAPPING_COLON,
                message="expected ':' after flow mapping key",
                source_name=source_name,
            )

        key = _parse_scalar(
            entry_token_array[:colon_index],
            version=version,
            source_name=source_name,
        ).value

        value = _parse_value(
            entry_token_array[colon_index + 1 :],
            version=version,
            source_name=source_name,
        )

        mapping.add_item(key, value)

    return mapping


def _find_matching_flow_end(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    start_index: int,
    start_type: korml.lexer.v1.TokenType,
    end_type: korml.lexer.v1.TokenType,
    source_name: str,
) -> int:
    depth = 0

    for index in range(start_index, len(token_array)):
        token_type = token_array[index].type

        if token_type is start_type:
            depth += 1
            continue

        if token_type is end_type:
            depth -= 1

            if depth == 0:
                return index

    raise _make_parse_error(
        ErrorCode.EXPECTED_VALUE,
        message=f"expected {end_type.value!r}",
        source_name=source_name,
    )


def _split_flow_item_token_arrays(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> list[tuple[korml.lexer.v1.Token, ...]]:
    item_array: list[tuple[korml.lexer.v1.Token, ...]] = []
    start = 0
    depth = 0

    for index, token in enumerate(token_array):
        if token.type in {
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
            korml.lexer.v1.TokenType.FLOW_MAPPING_START,
        }:
            depth += 1
            continue

        if token.type in {
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
            korml.lexer.v1.TokenType.FLOW_MAPPING_END,
        }:
            depth -= 1
            continue

        if token.type is korml.lexer.v1.TokenType.FLOW_SEPARATOR and depth == 0:
            item_array.append(tuple(token_array[start:index]))
            start = index + 1

    item_array.append(tuple(token_array[start:]))

    return item_array


def _find_top_level_flow_colon_index(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
) -> int | None:
    depth = 0

    for index, token in enumerate(token_array):
        if token.type in {
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_START,
            korml.lexer.v1.TokenType.FLOW_MAPPING_START,
        }:
            depth += 1
            continue

        if token.type in {
            korml.lexer.v1.TokenType.FLOW_SEQUENCE_END,
            korml.lexer.v1.TokenType.FLOW_MAPPING_END,
        }:
            depth -= 1
            continue

        if token.type is korml.lexer.v1.TokenType.COLON and depth == 0:
            return index

    return None


def _parse_sequence(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Sequence[korml.lexer.v1.Token]:
    concrete_token_array = tuple(token_array)
    first_token = _first_non_trivia(concrete_token_array)

    if first_token is None or first_token.type is not korml.lexer.v1.TokenType.DASH_ITEM:
        raise _make_parse_error(
            ErrorCode.EXPECTED_SEQUENCE,
            message="expected sequence",
            source_name=source_name,
        )

    indent = first_token.span.start.column

    item_start_array = _find_block_sequence_item_start_array(
        concrete_token_array,
        indent=indent,
    )

    value_array: list[korml.model.Value[korml.lexer.v1.Token]] = []

    for item_index, dash_index in enumerate(item_start_array):
        value_start = dash_index + 1
        value_end = _find_block_sequence_item_end(
            concrete_token_array,
            item_start_array=item_start_array,
            item_index=item_index,
            indent=indent,
        )

        value_array.append(
            _parse_value(
                concrete_token_array[value_start:value_end],
                version=version,
                source_name=source_name,
            )
        )

    return korml.model.Sequence[korml.lexer.v1.Token](
        value_array=value_array,
        style=korml.model.Style.block,
        cst=korml.model.CST(
            version=version,
            token_array=concrete_token_array,
        ),
    )


def _parse_mapping(
    token_array: collections.abc.Sequence[korml.lexer.v1.Token],
    *,
    version: korml.model.Version,
    source_name: str,
) -> korml.model.Mapping[korml.lexer.v1.Token]:
    concrete_token_array = tuple(token_array)
    first_token = _first_non_trivia(concrete_token_array)

    if first_token is None or first_token.type not in _SCALAR_TOKEN_TYPE_SET:
        raise _make_parse_error(
            ErrorCode.EXPECTED_MAPPING,
            message="expected mapping",
            source_name=source_name,
        )

    indent = first_token.span.start.column

    entry_start_array = _find_block_mapping_entry_start_array(
        concrete_token_array,
        indent=indent,
    )

    if not entry_start_array:
        raise _make_parse_error(
            ErrorCode.EXPECTED_MAPPING,
            message="expected mapping",
            source_name=source_name,
        )

    mapping = korml.model.Mapping[korml.lexer.v1.Token](
        style=korml.model.Style.block,
        cst=korml.model.CST(
            version=version,
            token_array=concrete_token_array,
        ),
    )

    for entry_index, key_index in enumerate(entry_start_array):
        entry_end = _find_block_mapping_entry_end(
            concrete_token_array,
            entry_start_array=entry_start_array,
            entry_index=entry_index,
            indent=indent,
        )

        colon_index = _find_mapping_colon_index(
            concrete_token_array,
            key_index=key_index,
            end=entry_end,
            source_name=source_name,
        )

        key = _parse_scalar(
            concrete_token_array[key_index:colon_index],
            version=version,
            source_name=source_name,
        ).value

        value = _parse_value(
            concrete_token_array[colon_index + 1 : entry_end],
            version=version,
            source_name=source_name,
        )

        mapping.add_item(key, value)

    return mapping
