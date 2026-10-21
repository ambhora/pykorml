# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import collections.abc
import dataclasses
import enum
import typing

import korml.core

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
    "Stream",
]


class Version(str, enum.Enum):
    unknown = "unknown"
    v0 = "v0"
    v1 = "v1"


class Style(str, enum.Enum):
    auto = "auto"
    flow = "flow"
    block = "block"


class GenericToken(typing.Protocol):
    type: object
    value: str
    span: korml.core.Span


ConcreteToken = typing.TypeVar("ConcreteToken", bound=GenericToken)


@dataclasses.dataclass(frozen=True, slots=True)
class CST(typing.Generic[ConcreteToken]):
    version: Version = Version.unknown
    token_array: tuple[ConcreteToken, ...] = ()

    @property
    def source(self) -> str:
        return "".join(token.value for token in self.token_array)

    @property
    def span(self) -> korml.core.Span:
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


@dataclasses.dataclass(slots=True, kw_only=True)
class Value(typing.Generic[ConcreteToken]):
    cst: CST[ConcreteToken] = dataclasses.field(
        default_factory=CST,
        compare=False,
    )

    def __post_init__(self) -> None:
        _check_value_array_version(
            parent_version=self.version,
            value_array=self.child_array,
        )

    @property
    def child_array(self) -> tuple["Value[ConcreteToken]", ...]:
        return ()

    @property
    def version(self) -> Version:
        return self.cst.version

    @property
    def token_array(self) -> tuple[ConcreteToken, ...]:
        return self.cst.token_array

    @property
    def source(self) -> str:
        return self.cst.source

    @property
    def span(self) -> korml.core.Span:
        return self.cst.span

    def to_builtin(self) -> object:
        raise NotImplementedError(f"{type(self).__name__}.to_builtin() is not implemented")

    def with_style(
        self,
        style: Style,
    ) -> "Value[ConcreteToken]":
        raise NotImplementedError(
            "flow/block CST conversion must be implemented by the "
            "version-specific lexer/CST generator"
        )

    def to_flow(self) -> "Value[ConcreteToken]":
        return self.with_style(Style.flow)

    def to_block(self) -> "Value[ConcreteToken]":
        return self.with_style(Style.block)


@dataclasses.dataclass(slots=True)
class Scalar(Value[ConcreteToken]):
    value: str = ""

    def to_builtin(self) -> str:
        return self.value


@dataclasses.dataclass(slots=True)
class Sequence(Value[ConcreteToken], collections.abc.Sequence[Value[ConcreteToken]]):
    value_array: list[Value[ConcreteToken]] = dataclasses.field(default_factory=list)
    style: Style = dataclasses.field(
        default=Style.auto,
        compare=False,
    )

    @property
    def child_array(self) -> tuple[Value[ConcreteToken], ...]:
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
        if not isinstance(value, Value):
            raise TypeError("append() only accepts KORML values")

        _check_value_version(
            parent_version=self.version,
            child=value,
        )

        self.value_array.append(value)

    def to_builtin(self) -> list[object]:
        return [value.to_builtin() for value in self.value_array]


@dataclasses.dataclass(slots=True)
class Mapping(Value[ConcreteToken], collections.abc.Mapping[str, Value[ConcreteToken]]):
    value_map: dict[str, Value[ConcreteToken]] = dataclasses.field(default_factory=dict)
    style: Style = dataclasses.field(
        default=Style.auto,
        compare=False,
    )

    @property
    def child_array(self) -> tuple[Value[ConcreteToken], ...]:
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
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")

        if not isinstance(value, Value):
            raise TypeError("add_item() only accepts KORML values")

        _check_value_version(
            parent_version=self.version,
            child=value,
        )

        self.value_map[key] = value

    def to_builtin(self) -> dict[str, object]:
        return {key: value.to_builtin() for key, value in self.value_map.items()}


@dataclasses.dataclass(slots=True)
class Stream(typing.Generic[ConcreteToken]):
    document_array: list[Value[ConcreteToken]] = dataclasses.field(default_factory=list)
    filename: str = ""
    cst: CST[ConcreteToken] = dataclasses.field(
        default_factory=CST,
        compare=False,
    )

    def __post_init__(self) -> None:
        _check_value_array_version(
            parent_version=self.version,
            value_array=self.document_array,
        )

    @property
    def version(self) -> Version:
        return self.cst.version

    @property
    def token_array(self) -> tuple[ConcreteToken, ...]:
        return self.cst.token_array

    @property
    def source(self) -> str:
        return self.cst.source

    @property
    def span(self) -> korml.core.Span:
        return self.cst.span

    def __len__(self) -> int:
        return len(self.document_array)

    def __getitem__(self, index: int) -> Value[ConcreteToken]:
        return self.document_array[index]

    def append(
        self,
        value: Value[ConcreteToken],
    ) -> None:
        if not isinstance(value, Value):
            raise TypeError("append() only accepts KORML values")

        _check_value_version(
            parent_version=self.version,
            child=value,
        )

        self.document_array.append(value)

    def to_builtin(self) -> list[object]:
        return [document.to_builtin() for document in self.document_array]


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
