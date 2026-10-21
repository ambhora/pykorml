# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Compile, validate, and construct values with the KORML schema v1 language."""

import collections.abc
import dataclasses
import enum
import re
import typing

__all__ = [
    "ErrorCode",
    "ValidationError",
    "SchemaError",
    "ConstructionError",
    "TypeReference",
    "TypeDefinition",
    "Schema",
    "compile_schema",
    "validate",
    "construct",
]

Builtin = str | list[typing.Any] | dict[str, typing.Any]

_SCHEMA_VERSION = "korml.schema.v1"
_SUPPORTED_KIND_SET = {"any", "scalar", "sequence", "mapping", "enum"}
_SUPPORTED_SCALAR_SET = {"string", "integer", "float", "boolean"}
_INTEGER_PATTERN = re.compile(r"[+-]?[0-9]+\Z")
_FLOAT_PATTERN = re.compile(r"[+-]?(?:([0-9]+(?:\.[0-9]*)?)|(\.[0-9]+))(?:[eE][+-]?[0-9]+)?\Z")


class ErrorCode(str, enum.Enum):
    """Stable diagnostic codes emitted by schema validation and construction."""

    INVALID_SCHEMA = "INVALID_SCHEMA"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    WRONG_KIND = "WRONG_KIND"
    MISSING_FIELD = "MISSING_FIELD"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    INVALID_SCALAR = "INVALID_SCALAR"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_ENUM_VALUE = "INVALID_ENUM_VALUE"
    CONSTRUCTION_FAILED = "CONSTRUCTION_FAILED"


@dataclasses.dataclass(frozen=True, slots=True)
class ValidationError:
    """A structured schema diagnostic at a builtin-value path."""

    code: ErrorCode
    path: tuple[str | int, ...]
    message: str


class SchemaError(ValueError):
    """Raised when a schema specification is malformed or inconsistent."""

    pass


class ConstructionError(ValueError):
    """Raised when validation or user construction fails during schema construction."""

    def __init__(self, error_array: collections.abc.Sequence[ValidationError]) -> None:
        """Store validation errors and format them as exception text."""
        self.error_array = tuple(error_array)
        super().__init__("\n".join(error.message for error in self.error_array))


@dataclasses.dataclass(frozen=True, slots=True)
class TypeReference:
    """A reference to a named schema type."""

    name: str


@dataclasses.dataclass(frozen=True, slots=True)
class TypeDefinition:
    """A compiled named schema type and its builtin-shape rules."""

    name: str
    kind: str
    scalar: str = "string"
    required: tuple[str, ...] = ()
    fields: dict[str, TypeReference] = dataclasses.field(default_factory=dict)
    items: TypeReference | None = None
    values: TypeReference | None = None
    enum: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Schema:
    """A compiled KORML schema with a root type and named type definitions."""

    version: str
    root: TypeReference
    types: dict[str, TypeDefinition]


def compile_schema(value: Builtin) -> Schema:
    """Compile a KORML builtin schema document into a checked schema object."""
    if not isinstance(value, dict):
        raise SchemaError("schema document must be a mapping")

    schema_version = value.get("schema")
    if schema_version != _SCHEMA_VERSION:
        raise SchemaError("schema field must be 'korml.schema.v1'")

    root_value = value.get("root")
    if root_value is None:
        raise SchemaError("schema document must contain root")

    root = _compile_type_reference(root_value, ("root",))

    types_value = value.get("types")
    if types_value is None:
        raise SchemaError("schema document must contain types")

    if not isinstance(types_value, dict):
        raise SchemaError("types must be a mapping")

    type_map: dict[str, TypeDefinition] = {}

    for type_name, definition_value in types_value.items():
        if not isinstance(type_name, str):
            raise SchemaError("type names must be strings")

        if not isinstance(definition_value, dict):
            raise SchemaError(f"types.{type_name} must be a mapping")

        type_map[type_name] = _compile_type_definition(type_name, definition_value)

    schema = Schema(
        version=_SCHEMA_VERSION,
        root=root,
        types=type_map,
    )

    _check_reference_exists(schema, schema.root, ("root", "type"))

    for type_definition in schema.types.values():
        _check_type_definition_references(schema, type_definition)
        _check_type_definition_consistency(type_definition)

    return schema


def validate(value: Builtin, schema: Schema) -> list[ValidationError]:
    """Validate a KORML builtin value against the schema root type."""
    _check_schema_type(schema)
    return _validate_type(
        value=value,
        schema=schema,
        type_name=schema.root.name,
        path=(),
    )


def construct(
    value: Builtin,
    schema: Schema,
    constructor_map: collections.abc.Mapping[str, collections.abc.Callable[..., object]]
    | None = None,
) -> object:
    """Validate a builtin value and recursively build user-defined objects."""
    _check_schema_type(schema)

    if constructor_map is None:
        constructor_map = {}

    error_array = validate(value, schema)

    if error_array:
        raise ConstructionError(error_array)

    try:
        return _construct_type(
            value=value,
            schema=schema,
            type_name=schema.root.name,
            constructor_map=constructor_map,
        )
    except Exception as error:
        raise ConstructionError(
            [
                ValidationError(
                    code=ErrorCode.CONSTRUCTION_FAILED,
                    path=(),
                    message=str(error),
                )
            ]
        ) from error


def _compile_type_definition(
    name: str,
    value: dict[str, typing.Any],
) -> TypeDefinition:
    """Compile one named type definition from the schema builtin mapping."""
    kind = value.get("kind")
    if not isinstance(kind, str):
        raise SchemaError(f"types.{name}.kind must be a string")

    if kind not in _SUPPORTED_KIND_SET:
        raise SchemaError(f"types.{name}.kind has unsupported value {kind!r}")

    scalar = value.get("scalar", "string")
    if not isinstance(scalar, str):
        raise SchemaError(f"types.{name}.scalar must be a string")

    if scalar not in _SUPPORTED_SCALAR_SET:
        raise SchemaError(f"types.{name}.scalar has unsupported value {scalar!r}")

    return TypeDefinition(
        name=name,
        kind=kind,
        scalar=scalar,
        required=_compile_required(value.get("required", []), name),
        fields=_compile_fields(value.get("fields", {}), name),
        items=_compile_optional_type_reference(value, "items", ("types", name, "items")),
        values=_compile_optional_type_reference(value, "values", ("types", name, "values")),
        enum=_compile_enum(value.get("enum", []), name),
        minimum=_compile_optional_integer(value.get("minimum"), ("types", name, "minimum")),
        maximum=_compile_optional_integer(value.get("maximum"), ("types", name, "maximum")),
    )


def _compile_required(value: typing.Any, type_name: str) -> tuple[str, ...]:
    """Compile the required-field sequence for a mapping type."""
    if not isinstance(value, list):
        raise SchemaError(f"types.{type_name}.required must be a sequence")

    required_array: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise SchemaError(f"types.{type_name}.required[{index}] must be a string")

        required_array.append(item)

    return tuple(required_array)


def _compile_fields(value: typing.Any, type_name: str) -> dict[str, TypeReference]:
    """Compile the named-field map for a mapping type."""
    if not isinstance(value, dict):
        raise SchemaError(f"types.{type_name}.fields must be a mapping")

    field_map: dict[str, TypeReference] = {}

    for field_name, reference_value in value.items():
        if not isinstance(field_name, str):
            raise SchemaError(f"types.{type_name}.fields keys must be strings")

        field_map[field_name] = _compile_type_reference(
            reference_value,
            ("types", type_name, "fields", field_name),
        )

    return field_map


def _compile_enum(value: typing.Any, type_name: str) -> tuple[str, ...]:
    """Compile the allowed string values for an enum type."""
    if not isinstance(value, list):
        raise SchemaError(f"types.{type_name}.enum must be a sequence")

    enum_array: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise SchemaError(f"types.{type_name}.enum[{index}] must be a string")

        enum_array.append(item)

    return tuple(enum_array)


def _compile_optional_type_reference(
    value: dict[str, typing.Any],
    key: str,
    path: tuple[str | int, ...],
) -> TypeReference | None:
    """Compile an optional nested type reference field."""
    if key not in value:
        return None

    return _compile_type_reference(value[key], path)


def _compile_type_reference(
    value: typing.Any,
    path: tuple[str | int, ...],
) -> TypeReference:
    """Compile a mapping of the form {type: TypeName}."""
    if not isinstance(value, dict):
        raise SchemaError(f"{_format_path(path)} must be a mapping")

    type_name = value.get("type")
    if not isinstance(type_name, str):
        raise SchemaError(f"{_format_path(path + ('type',))} must be a string")

    return TypeReference(type_name)


def _compile_optional_integer(
    value: typing.Any,
    path: tuple[str | int, ...],
) -> int | None:
    """Compile an optional integer scalar from schema builtin text."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise SchemaError(f"{_format_path(path)} must be an integer scalar")

    if not _INTEGER_PATTERN.fullmatch(value):
        raise SchemaError(f"{_format_path(path)} must be an integer scalar")

    return int(value)


def _check_reference_exists(
    schema: Schema,
    reference: TypeReference,
    path: tuple[str | int, ...],
) -> None:
    """Ensure that a type reference points at a declared schema type."""
    if reference.name not in schema.types:
        raise SchemaError(f"{_format_path(path)} references unknown type {reference.name!r}")


def _check_type_definition_references(
    schema: Schema,
    type_definition: TypeDefinition,
) -> None:
    """Check all nested type references used by a type definition."""
    for field_name, reference in type_definition.fields.items():
        _check_reference_exists(
            schema,
            reference,
            ("types", type_definition.name, "fields", field_name, "type"),
        )

    if type_definition.items is not None:
        _check_reference_exists(
            schema,
            type_definition.items,
            ("types", type_definition.name, "items", "type"),
        )

    if type_definition.values is not None:
        _check_reference_exists(
            schema,
            type_definition.values,
            ("types", type_definition.name, "values", "type"),
        )


def _check_type_definition_consistency(type_definition: TypeDefinition) -> None:
    """Check kind-specific invariants within a type definition."""
    if type_definition.kind == "sequence" and type_definition.items is None:
        raise SchemaError(f"types.{type_definition.name}.items is required for sequence types")

    if type_definition.kind == "enum" and not type_definition.enum:
        raise SchemaError(f"types.{type_definition.name}.enum is required for enum types")

    if type_definition.kind == "mapping":
        for required_name in type_definition.required:
            if required_name not in type_definition.fields:
                raise SchemaError(
                    f"types.{type_definition.name}.required contains unknown field {required_name!r}"
                )

    if type_definition.minimum is not None and type_definition.maximum is not None:
        if type_definition.minimum > type_definition.maximum:
            raise SchemaError(
                f"types.{type_definition.name}.minimum must be less than or equal to maximum"
            )


def _validate_type(
    *,
    value: Builtin,
    schema: Schema,
    type_name: str,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """Dispatch validation for one value against a named schema type."""
    type_definition = schema.types.get(type_name)

    if type_definition is None:
        return [
            ValidationError(
                code=ErrorCode.UNKNOWN_TYPE,
                path=path,
                message=f"unknown type {type_name!r}",
            )
        ]

    match type_definition.kind:
        case "any":
            return []

        case "scalar":
            return _validate_scalar(value, type_definition, path)

        case "sequence":
            return _validate_sequence(value, schema, type_definition, path)

        case "mapping":
            return _validate_mapping(value, schema, type_definition, path)

        case "enum":
            return _validate_enum(value, type_definition, path)

        case _:
            return [
                ValidationError(
                    code=ErrorCode.INVALID_SCHEMA,
                    path=path,
                    message=f"unsupported type kind {type_definition.kind!r}",
                )
            ]


def _validate_scalar(
    value: Builtin,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """Validate a builtin scalar string against scalar subtype rules."""
    if not isinstance(value, str):
        return [
            ValidationError(
                code=ErrorCode.WRONG_KIND,
                path=path,
                message=f"expected scalar for {type_definition.name}",
            )
        ]

    if type_definition.scalar == "string":
        return []

    if type_definition.scalar == "integer":
        return _validate_integer_scalar(value, type_definition, path)

    if type_definition.scalar == "boolean":
        if value in {"true", "false"}:
            return []

        return [
            ValidationError(
                code=ErrorCode.INVALID_SCALAR,
                path=path,
                message=f"expected boolean scalar for {type_definition.name}",
            )
        ]

    if type_definition.scalar == "float":
        if _FLOAT_PATTERN.fullmatch(value):
            return []

        return [
            ValidationError(
                code=ErrorCode.INVALID_SCALAR,
                path=path,
                message=f"expected float scalar for {type_definition.name}",
            )
        ]

    return [
        ValidationError(
            code=ErrorCode.INVALID_SCHEMA,
            path=path,
            message=f"unsupported scalar kind {type_definition.scalar!r}",
        )
    ]


def _validate_integer_scalar(
    value: str,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """Validate integer spelling and optional integer range bounds."""
    if not _INTEGER_PATTERN.fullmatch(value):
        return [
            ValidationError(
                code=ErrorCode.INVALID_SCALAR,
                path=path,
                message=f"expected integer scalar for {type_definition.name}",
            )
        ]

    integer = int(value)

    if type_definition.minimum is not None and integer < type_definition.minimum:
        return [
            ValidationError(
                code=ErrorCode.OUT_OF_RANGE,
                path=path,
                message=f"integer scalar for {type_definition.name} is below minimum",
            )
        ]

    if type_definition.maximum is not None and integer > type_definition.maximum:
        return [
            ValidationError(
                code=ErrorCode.OUT_OF_RANGE,
                path=path,
                message=f"integer scalar for {type_definition.name} is above maximum",
            )
        ]

    return []


def _validate_sequence(
    value: Builtin,
    schema: Schema,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """Validate a builtin sequence and each item against its item type."""
    if not isinstance(value, list):
        return [
            ValidationError(
                code=ErrorCode.WRONG_KIND,
                path=path,
                message=f"expected sequence for {type_definition.name}",
            )
        ]

    if type_definition.items is None:
        return [
            ValidationError(
                code=ErrorCode.INVALID_SCHEMA,
                path=path,
                message=f"sequence type {type_definition.name} has no items type",
            )
        ]

    error_array: list[ValidationError] = []

    for index, item in enumerate(value):
        error_array.extend(
            _validate_type(
                value=item,
                schema=schema,
                type_name=type_definition.items.name,
                path=path + (index,),
            )
        )

    return error_array


def _validate_mapping(
    value: Builtin,
    schema: Schema,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """Validate a builtin mapping against required, field, and value rules."""
    if not isinstance(value, dict):
        return [
            ValidationError(
                code=ErrorCode.WRONG_KIND,
                path=path,
                message=f"expected mapping for {type_definition.name}",
            )
        ]

    error_array: list[ValidationError] = []

    for required_name in type_definition.required:
        if required_name not in value:
            error_array.append(
                ValidationError(
                    code=ErrorCode.MISSING_FIELD,
                    path=path + (required_name,),
                    message=f"missing required field {required_name!r}",
                )
            )

    for key, child in value.items():
        reference = type_definition.fields.get(key)

        if reference is None:
            reference = type_definition.values

        if reference is None:
            error_array.append(
                ValidationError(
                    code=ErrorCode.UNKNOWN_FIELD,
                    path=path + (key,),
                    message=f"unknown field {key!r}",
                )
            )
            continue

        error_array.extend(
            _validate_type(
                value=child,
                schema=schema,
                type_name=reference.name,
                path=path + (key,),
            )
        )

    return error_array


def _validate_enum(
    value: Builtin,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """Validate a builtin scalar against an enum value set."""
    if not isinstance(value, str):
        return [
            ValidationError(
                code=ErrorCode.WRONG_KIND,
                path=path,
                message=f"expected scalar enum for {type_definition.name}",
            )
        ]

    if value in type_definition.enum:
        return []

    return [
        ValidationError(
            code=ErrorCode.INVALID_ENUM_VALUE,
            path=path,
            message=f"invalid enum value {value!r} for {type_definition.name}",
        )
    ]


def _construct_type(
    *,
    value: Builtin,
    schema: Schema,
    type_name: str,
    constructor_map: collections.abc.Mapping[str, collections.abc.Callable[..., object]],
) -> object:
    """Construct one value by first constructing children, then applying a constructor."""
    type_definition = schema.types[type_name]

    match type_definition.kind:
        case "any":
            constructed = value

        case "scalar" | "enum":
            constructed = value

        case "sequence":
            assert type_definition.items is not None
            assert isinstance(value, list)
            constructed = [
                _construct_type(
                    value=item,
                    schema=schema,
                    type_name=type_definition.items.name,
                    constructor_map=constructor_map,
                )
                for item in value
            ]

        case "mapping":
            assert isinstance(value, dict)
            constructed_map: dict[str, object] = {}

            for key, child in value.items():
                reference = type_definition.fields.get(key, type_definition.values)

                if reference is None:
                    continue

                constructed_map[key] = _construct_type(
                    value=child,
                    schema=schema,
                    type_name=reference.name,
                    constructor_map=constructor_map,
                )

            constructed = constructed_map

        case _:
            raise SchemaError(f"unsupported type kind {type_definition.kind!r}")

    constructor = constructor_map.get(type_name)

    if constructor is None:
        return constructed

    if type_definition.kind == "mapping":
        assert isinstance(constructed, dict)
        return constructor(**constructed)

    return constructor(constructed)


def _check_schema_type(schema: Schema) -> None:
    """Reject non-v1 schema objects passed into v1 API functions."""
    if not isinstance(schema, Schema):
        raise TypeError("schema must be a compiled korml.schema.v1.Schema")


def _format_path(path: tuple[str | int, ...]) -> str:
    """Format a diagnostic path as compact dotted/indexed text."""
    if not path:
        return "<root>"

    text = str(path[0])

    for part in path[1:]:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}"

    return text
