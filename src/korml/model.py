# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc
import dataclasses
import enum
import typing

import korml._limits
import korml.core
import korml.error

__all__ = [
    "Version",
    "Style",
    "GenericToken",
    "ConcreteToken",
    "CST",
    "Value",
    "Scalar",
    "Sequence",
    "Mapping",
    "Empty",
    "Stream",
]


class Version(str, enum.Enum):
    """The versions of the Korml language."""

    unknown = "unknown"
    """No version, the state of a value built without one."""
    v0 = "v0"
    """Korml v0, the single-document source form."""
    v1 = "v1"
    """Korml v1, with a version directive and document markers."""


class Style(str, enum.Enum):
    """How a collection is written."""

    auto = "auto"
    """No particular style, the state of a value built in code."""
    flow = "flow"
    """On one line, between brackets or braces."""
    block = "block"
    """On lines of its own, by indentation."""


class GenericToken(typing.Protocol):
    """What the model needs of a token."""

    type: object
    """The kind of token."""
    value: str
    """The exact source text of the token."""
    span: korml.core.Span
    """Where the token is."""


ConcreteToken = typing.TypeVar("ConcreteToken", bound=GenericToken)
"""The token type of a model, such as korml.lexer.v1.Token."""


@dataclasses.dataclass(frozen=True, slots=True)
class CST(typing.Generic[ConcreteToken]):
    """The concrete tokens a value was read from."""

    version: Version = Version.unknown
    """The language version of the tokens."""
    token_array: tuple[ConcreteToken, ...] = ()
    """The tokens, in source order."""

    @property
    def source(self) -> str:
        """The source text of the tokens."""
        return "".join(token.value for token in self.token_array)

    @property
    def span(self) -> korml.core.Span:
        """The span from the first token to the last, or an empty span if there are none."""
        if not self.token_array:
            return korml.core.Span.empty()

        return korml.core.Span(
            start=self.token_array[0].span.start,
            end=self.token_array[-1].span.end,
        )


def _make_empty_cst(
    *,
    version: Version,
) -> CST[ConcreteToken]:
    return CST(
        version=version,
        token_array=(),
    )


def _check_value_version(
    *,
    parent_version: Version,
    child: "Value[ConcreteToken]",
) -> None:
    if child.version != parent_version:
        raise ValueError(
            f"value version {child.version.value!r} does not match "
            f"parent version {parent_version.value!r}"
        )


def _check_value_array_version(
    *,
    parent_version: Version,
    value_array: collections.abc.Iterable["Value[ConcreteToken]"],
) -> None:
    for value in value_array:
        _check_value_version(
            parent_version=parent_version,
            child=value,
        )


def _check_not_empty(child: "Value[ConcreteToken]") -> None:
    """Refuse an Empty as a mapping value or sequence entry; it is only a document root."""
    if isinstance(child, Empty):
        raise TypeError("an empty document can only be the root of a document")


def _too_deep_error(max_depth: int | None) -> korml.error.KormlError:
    return korml.error.KormlError(
        message=korml._limits.too_deep_message(max_depth),
        code="TOO_DEEP",
    )


def _builtin_of(
    value: "Value[ConcreteToken]",
    *,
    depth: int,
    max_depth: int | None,
) -> object:
    """Convert value to plain Python data; depth counts the collections around it."""
    if isinstance(value, (Sequence, Mapping)) and korml._limits.is_too_deep(depth, max_depth):
        raise _too_deep_error(max_depth)

    if isinstance(value, Sequence):
        return [
            _builtin_of(child, depth=depth + 1, max_depth=max_depth) for child in value.value_array
        ]

    if isinstance(value, Mapping):
        return {
            key: _builtin_of(child, depth=depth + 1, max_depth=max_depth)
            for key, child in value.value_map.items()
        }

    return value.to_builtin()


def _to_builtin(value: "Value[ConcreteToken]", *, max_depth: int | None) -> object:
    """
    Convert a value, refusing nesting deeper than max_depth with a TOO_DEEP error.

    With max_depth None, a RecursionError from Python becomes the same error.
    """
    korml._limits.check_max_depth(max_depth)

    try:
        return _builtin_of(value, depth=0, max_depth=max_depth)
    except RecursionError as error:
        raise _too_deep_error(max_depth) from error


@dataclasses.dataclass(slots=True, kw_only=True)
class Value(typing.Generic[ConcreteToken]):
    """A value of a document; base class of Scalar, Sequence, Mapping and Empty."""

    cst: CST[ConcreteToken] = dataclasses.field(
        default_factory=CST,
        compare=False,
    )
    """The tokens the value was read from; they do not count when comparing values."""

    def __post_init__(self) -> None:
        _check_value_array_version(
            parent_version=self.version,
            value_array=self.child_array,
        )

        for child in self.child_array:
            _check_not_empty(child)

    @property
    def child_array(self) -> tuple["Value[ConcreteToken]", ...]:
        """The values directly inside this one."""
        return ()

    @property
    def version(self) -> Version:
        """The language version of the value."""
        return self.cst.version

    @property
    def token_array(self) -> tuple[ConcreteToken, ...]:
        """The concrete tokens of the value."""
        return self.cst.token_array

    @property
    def source(self) -> str:
        """The source text of the value."""
        return self.cst.source

    @property
    def span(self) -> korml.core.Span:
        """The span of the value."""
        return self.cst.span

    def to_builtin(self, *, max_depth: int | None = korml._limits.MAX_NESTING_DEPTH) -> object:
        """
        Return the value as plain Python data: dict, list, str, or None for Empty.

        max_depth is the deepest nesting of collections converted; deeper
        nesting raises a KormlError with the code TOO_DEEP. None removes
        the limit, and a RecursionError from Python raises the same error.
        """
        raise NotImplementedError(f"{type(self).__name__}.to_builtin() is not implemented")

    def with_style(
        self,
        style: Style,
    ) -> "Value[ConcreteToken]":
        """Return the value in another style; no version implements this yet."""
        raise NotImplementedError(
            "flow/block CST conversion must be implemented by the "
            "version-specific lexer/CST generator"
        )

    def to_flow(self) -> "Value[ConcreteToken]":
        """Return the value in flow style; see with_style."""
        return self.with_style(Style.flow)

    def to_block(self) -> "Value[ConcreteToken]":
        """Return the value in block style; see with_style."""
        return self.with_style(Style.block)


@dataclasses.dataclass(slots=True)
class Scalar(Value[ConcreteToken]):
    """A scalar: a string and the tokens it was read from."""

    value: str = ""
    """The string the scalar denotes. Every Korml scalar is text."""

    def to_builtin(self, *, max_depth: int | None = korml._limits.MAX_NESTING_DEPTH) -> str:
        """Return the string of the scalar; max_depth is only validated."""
        korml._limits.check_max_depth(max_depth)
        return self.value


@dataclasses.dataclass(slots=True)
class Sequence(Value[ConcreteToken], collections.abc.Sequence[Value[ConcreteToken]]):
    """A sequence of values."""

    value_array: list[Value[ConcreteToken]] = dataclasses.field(default_factory=list)
    """The values, in order."""
    style: Style = dataclasses.field(
        default=Style.auto,
        compare=False,
    )
    """How the sequence is written; it does not count when comparing values."""

    @property
    def child_array(self) -> tuple[Value[ConcreteToken], ...]:
        """The values of the sequence."""
        return tuple(self.value_array)

    def __len__(self) -> int:
        return len(self.value_array)

    def __getitem__(self, index: int) -> Value[ConcreteToken]:
        return self.value_array[index]

    def __setitem__(self, index: int, value: object) -> None:
        self.value_array[index] = _make_value_from_raw(
            value,
            version=self.version,
        )

    def append(
        self,
        value: Value[ConcreteToken],
    ) -> None:
        """Add a value at the end, refusing another version or an Empty."""
        if not isinstance(value, Value):
            raise TypeError("append() only accepts KORML values")

        _check_value_version(
            parent_version=self.version,
            child=value,
        )
        _check_not_empty(value)

        self.value_array.append(value)

    def to_builtin(
        self, *, max_depth: int | None = korml._limits.MAX_NESTING_DEPTH
    ) -> list[object]:
        """Return the sequence as a list; see Value.to_builtin."""
        return typing.cast(list[object], _to_builtin(self, max_depth=max_depth))


@dataclasses.dataclass(slots=True)
class Mapping(Value[ConcreteToken], collections.abc.Mapping[str, Value[ConcreteToken]]):
    """A mapping from strings to values, in source order."""

    value_map: dict[str, Value[ConcreteToken]] = dataclasses.field(default_factory=dict)
    """The entries, in order."""
    style: Style = dataclasses.field(
        default=Style.auto,
        compare=False,
    )
    """How the mapping is written; it does not count when comparing values."""

    @property
    def child_array(self) -> tuple[Value[ConcreteToken], ...]:
        """The values of the mapping."""
        return tuple(self.value_map.values())

    def __len__(self) -> int:
        return len(self.value_map)

    def __iter__(self) -> collections.abc.Iterator[str]:
        return iter(self.value_map)

    def __getitem__(self, key: str) -> Value[ConcreteToken]:
        return self.value_map[key]

    def __setitem__(self, key: str, value: object) -> None:
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")

        self.value_map[key] = _make_value_from_raw(
            value,
            version=self.version,
        )

    def add_item(
        self,
        key: str,
        value: Value[ConcreteToken],
    ) -> None:
        """Set the value of key, refusing another version or an Empty."""
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")

        if not isinstance(value, Value):
            raise TypeError("add_item() only accepts KORML values")

        _check_value_version(
            parent_version=self.version,
            child=value,
        )
        _check_not_empty(value)

        self.value_map[key] = value

    def to_builtin(
        self, *, max_depth: int | None = korml._limits.MAX_NESTING_DEPTH
    ) -> dict[str, object]:
        """Return the mapping as a dict; see Value.to_builtin."""
        return typing.cast(dict[str, object], _to_builtin(self, max_depth=max_depth))


@dataclasses.dataclass(slots=True)
class Empty(Value[ConcreteToken]):
    """
    The root of a document that has no root node.

    A document has zero or one root node: '---' then '...' in v1, or an empty
    or blank-only v0 source, is a document with none. Empty stands in that
    document's place in Stream.document_array, so a stream keeps every
    document it was read from, and its CST keeps the tokens of the empty
    body, such as the comments between the markers. The name follows
    Scalar, Sequence and Mapping, which name what a document holds; this
    one holds nothing.

    Empty is not a value of the language: it is only ever a document root,
    and the model refuses it as a mapping value or sequence entry.
    to_builtin returns None, the only place None appears, so that a stream
    converts to plain Python data.
    """

    def to_builtin(self, *, max_depth: int | None = korml._limits.MAX_NESTING_DEPTH) -> None:
        """Return None; max_depth is only validated."""
        korml._limits.check_max_depth(max_depth)
        return None


@dataclasses.dataclass(slots=True)
class Stream(typing.Generic[ConcreteToken]):
    """The documents of a source, with every token it was read from."""

    document_array: list[Value[ConcreteToken]] = dataclasses.field(default_factory=list)
    """The documents, an Empty for each document without a root node."""
    filename: str = ""
    """The name of the source."""
    cst: CST[ConcreteToken] = dataclasses.field(
        default_factory=CST,
        compare=False,
    )
    """Every token of the source."""

    def __post_init__(self) -> None:
        _check_value_array_version(
            parent_version=self.version,
            value_array=self.document_array,
        )

    @property
    def version(self) -> Version:
        """The language version of the source."""
        return self.cst.version

    @property
    def token_array(self) -> tuple[ConcreteToken, ...]:
        """Every token of the source."""
        return self.cst.token_array

    @property
    def source(self) -> str:
        """The source text, exactly as it was read."""
        return self.cst.source

    @property
    def span(self) -> korml.core.Span:
        """The span of the source."""
        return self.cst.span

    def __len__(self) -> int:
        return len(self.document_array)

    def __getitem__(self, index: int) -> Value[ConcreteToken]:
        return self.document_array[index]

    def append(
        self,
        value: Value[ConcreteToken],
    ) -> None:
        """Add a document, refusing a value of another version."""
        if not isinstance(value, Value):
            raise TypeError("append() only accepts KORML values")

        _check_value_version(
            parent_version=self.version,
            child=value,
        )

        self.document_array.append(value)

    def to_builtin(
        self, *, max_depth: int | None = korml._limits.MAX_NESTING_DEPTH
    ) -> list[object]:
        """
        Return one plain Python value per document; None for an empty document.

        max_depth limits the nesting of each document; see Value.to_builtin.
        """
        return [_to_builtin(document, max_depth=max_depth) for document in self.document_array]


def _make_value_from_raw(
    value: object,
    *,
    version: Version,
) -> Value[ConcreteToken]:
    if isinstance(value, Value):
        raise TypeError(
            "raw assignment does not accept KORML values; use add_item() or append() instead"
        )

    if isinstance(value, str):
        return Scalar(
            value,
            cst=_make_empty_cst(version=version),
        )

    if isinstance(value, list):
        return Sequence(
            value_array=[
                _make_value_from_raw(
                    child,
                    version=version,
                )
                for child in value
            ],
            cst=_make_empty_cst(version=version),
        )

    if isinstance(value, dict):
        mapping = Mapping(
            cst=_make_empty_cst(version=version),
        )

        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("raw mapping keys must be strings")

            mapping[key] = child

        return mapping

    raise TypeError(f"cannot create KORML value from {type(value).__name__!r}")
