# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Compile, validate, and construct values with the KORML schema v1 language."""

import collections.abc
import dataclasses
import enum
import re
import typing

import korml._limits
import korml.error
import korml.model

__all__ = [
    "ErrorCode",
    "ValidationError",
    "SchemaError",
    "ConstructionError",
    "InvalidValueError",
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
    """A malformed or inconsistent schema."""
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    """A reference to a type the schema does not declare."""
    WRONG_KIND = "WRONG_KIND"
    """A value that is not the scalar, sequence or mapping its type wants."""
    MISSING_FIELD = "MISSING_FIELD"
    """A required field that is absent."""
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    """A field the type does not declare."""
    INVALID_SCALAR = "INVALID_SCALAR"
    """A scalar that is not the integer, float or boolean its type wants."""
    OUT_OF_RANGE = "OUT_OF_RANGE"
    """An integer below the minimum or above the maximum of its type."""
    INVALID_ENUM_VALUE = "INVALID_ENUM_VALUE"
    """A scalar that is none of the values of its enum."""
    CONSTRUCTION_FAILED = "CONSTRUCTION_FAILED"
    """A value that failed validation, or a constructor that failed."""
    TOO_DEEP = "TOO_DEEP"
    """A value nested deeper than max_depth."""
    CYCLIC_VALUE = "CYCLIC_VALUE"
    """A container that contains itself."""
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    """An empty document, for a root type that is not of kind any."""


@dataclasses.dataclass(frozen=True, slots=True)
class ValidationError:
    """A structured schema diagnostic at a builtin-value path."""

    code: ErrorCode
    """What is wrong."""
    path: tuple[str | int, ...]
    """Where it is: the keys and indices from the root to the value."""
    message: str
    """What is wrong, for a reader; it may quote the document."""
    unquoted_message: str | None = None
    """What is wrong, without text of the document; None if message quotes none of it."""


class SchemaError(korml.error.KormlError, ValueError):
    """Raised when a schema specification is malformed or inconsistent.

    A KormlError, so one except clause catches every korml failure, and a
    ValueError as before.
    """

    def __init__(self, message: str) -> None:
        """
        Initialize the error, escaping what message quotes from the schema.

        @param message What is wrong; it may quote the schema.
        """
        # Schema messages are one line and interpolate names from the schema
        # document, which may hold control characters.
        super().__init__(
            message=korml.error.escape_controls(message),
            code=ErrorCode.INVALID_SCHEMA.value,
        )


class ConstructionError(korml.error.KormlError, ValueError):
    """Raised when validation or user construction fails during schema construction.

    A KormlError, so one except clause catches every korml failure, and a
    ValueError as before.
    """

    def __init__(self, error_array: collections.abc.Sequence[ValidationError]) -> None:
        """
        Store validation errors and format them as exception text.

        @param error_array The validation errors, one line of the message each.
        """
        self.error_array = tuple(error_array)
        super().__init__(
            # One line per error; each line escaped on its own, since the
            # messages interpolate names from the schema document.
            message="\n".join(
                korml.error.escape_controls(error.message) for error in self.error_array
            ),
            code=ErrorCode.CONSTRUCTION_FAILED.value,
            unquoted_message="\n".join(
                korml.error.escape_controls(
                    error.message if error.unquoted_message is None else error.unquoted_message
                )
                for error in self.error_array
            ),
        )


class InvalidValueError(korml.error.KormlError, ValueError):
    """Raised when a value cannot be validated at all: it nests too deeply or contains itself.

    validate and construct walk a value along its schema types, once per
    level of nesting. A value nested deeper than korml reads or writes
    (korml._limits.MAX_NESTING_DEPTH), or a container that contains itself
    under a recursive schema type, would otherwise end in a RecursionError
    or never end. A KormlError and a ValueError, like the other schema errors.
    """

    def __init__(self, *, code: ErrorCode, path: tuple[str | int, ...], message: str) -> None:
        """
        Store the path of the offending value with the message.

        @param code The error code.

        @param path The path of the offending value.

        @param message What is wrong.
        """
        self.path = path
        super().__init__(
            message=f"{korml.error.escape_controls(_format_path(path))}: {message}",
            code=code.value,
            # The path is made of the keys of the document.
            unquoted_message=message,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class TypeReference:
    """A reference to a named schema type."""

    name: str
    """The name of the type."""


@dataclasses.dataclass(frozen=True, slots=True)
class TypeDefinition:
    """A compiled named schema type and its builtin-shape rules."""

    name: str
    """The name of the type."""
    kind: str
    """One of any, scalar, sequence, mapping or enum."""
    scalar: str = "string"
    """For a scalar type: string, integer, float or boolean."""
    required: tuple[str, ...] = ()
    """For a mapping type: the fields that must be present."""
    fields: dict[str, TypeReference] = dataclasses.field(default_factory=dict)
    """For a mapping type: the type of each declared field."""
    items: TypeReference | None = None
    """For a sequence type: the type of its items."""
    values: TypeReference | None = None
    """For a mapping type: the type of the entries that are not declared fields."""
    enum: tuple[str, ...] = ()
    """For an enum type: the values allowed."""
    minimum: int | None = None
    """For an integer scalar: the smallest value allowed."""
    maximum: int | None = None
    """For an integer scalar: the largest value allowed."""


@dataclasses.dataclass(frozen=True, slots=True)
class Schema:
    """A compiled KORML schema with a root type and named type definitions."""

    version: str
    """The schema language, korml.schema.v1."""
    root: TypeReference
    """The type of a document."""
    types: dict[str, TypeDefinition]
    """The named types."""


def compile_schema(value: Builtin) -> Schema:
    """
    Compile a KORML builtin schema document into a checked schema object.

    @param value The schema document as plain data.

    @return The schema.
    """
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


@dataclasses.dataclass(slots=True)
class _Walk:
    """What validation tracks along the path through a value."""

    max_depth: int | None
    active_id_set: set[int] = dataclasses.field(default_factory=set)


def _is_empty_document(value: object) -> bool:
    """
    Return whether value stands for an empty document.

    @param value The value.

    @return True for None and for an Empty.
    """
    return value is None or isinstance(value, korml.model.Empty)


def validate(
    value: Builtin | None,
    schema: Schema,
    *,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> list[ValidationError]:
    """
    Validate a KORML builtin value against the schema root type.

    Returns the list of validation errors, empty if the value is valid.

    An empty document, which to_builtin gives as None (or an Empty), has no
    value: it is valid only if the root type is of kind any, and otherwise
    gives one EMPTY_DOCUMENT error.

    max_depth is the deepest nesting of collections validated. Raises
    InvalidValueError for a value nested deeper or one that contains
    itself; with max_depth None, nesting too deep for Python's recursion
    limit raises it with the code TOO_DEEP too.

    @param value The plain data, or None for an empty document.

    @param schema The compiled schema.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The validation errors, empty if the value is valid.
    """
    _check_schema_type(schema)
    korml._limits.check_max_depth(max_depth)

    if _is_empty_document(value):
        if schema.types[schema.root.name].kind == "any":
            return []

        return [
            ValidationError(
                code=ErrorCode.EMPTY_DOCUMENT,
                path=(),
                message=f"the document is empty; expected a value of type {schema.root.name}",
            )
        ]

    try:
        return _validate_type(
            value=value,
            schema=schema,
            type_name=schema.root.name,
            path=(),
            walk=_Walk(max_depth=max_depth),
        )
    except RecursionError as error:
        raise _too_deep_error(max_depth) from error


def _too_deep_error(max_depth: int | None) -> InvalidValueError:
    """
    Return the error for nesting deeper than max_depth.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The error, with the code TOO_DEEP.
    """
    return InvalidValueError(
        code=ErrorCode.TOO_DEEP,
        path=(),
        message=korml._limits.too_deep_message(max_depth),
    )


def construct(
    value: Builtin | None,
    schema: Schema,
    constructor_map: collections.abc.Mapping[str, collections.abc.Callable[..., object]]
    | None = None,
    *,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> object:
    """
    Validate a builtin value and recursively build user-defined objects.

    constructor_map maps type names to callables. Children are constructed
    first; then the constructor of a type, if there is one, is called with
    the constructed value:

    - scalar, enum, any and sequence types: constructor(value);
    - mapping types without values: constructor(**fields), one keyword
      argument per declared field present in the document;
    - mapping types with values: constructor(entries, **fields), where
      entries is a dict of every entry that is not a declared field.

    Only declared fields become keyword arguments. Keys of the open-ended
    values entries come from the document, so passing them as keywords
    would let a document set any parameter of the constructor, such as
    sandbox in Job(cmd, sandbox=True); they are passed as one dict instead.

    An empty document (None or an Empty) constructs to None when the root
    type is of kind any, without calling a constructor, since there is
    nothing to construct; for any other root type it is a ConstructionError
    with an EMPTY_DOCUMENT error, as from validate.

    Raises ConstructionError if the value is invalid or a constructor
    fails, and InvalidValueError (see validate) for a value nested deeper
    than max_depth or containing itself. Construction follows the same path
    through the value as validation, which has already checked both.

    @param value The plain data, or None for an empty document.

    @param schema The compiled schema.

    @param constructor_map The constructor of each type name, or None for none.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The constructed value, or None for an empty document.
    """
    _check_schema_type(schema)

    if constructor_map is None:
        constructor_map = {}

    error_array = validate(value, schema, max_depth=max_depth)

    if error_array:
        raise ConstructionError(error_array)

    if _is_empty_document(value):
        return None

    try:
        return _construct_type(
            value=value,
            schema=schema,
            type_name=schema.root.name,
            constructor_map=constructor_map,
        )
    except RecursionError as error:
        raise _too_deep_error(max_depth) from error
    except Exception as error:
        raise ConstructionError(
            [
                ValidationError(
                    code=ErrorCode.CONSTRUCTION_FAILED,
                    path=(),
                    message=str(error),
                    # A constructor's own message may repeat the values it was given.
                    unquoted_message=f"a constructor raised {type(error).__name__}",
                )
            ]
        ) from error


def _compile_type_definition(
    name: str,
    value: dict[str, typing.Any],
) -> TypeDefinition:
    """
    Compile one named type definition from the schema builtin mapping.

    @param name The name of the type.

    @param value The definition as plain data.

    @return The type definition.
    """
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
    """
    Compile the required-field sequence for a mapping type.

    @param value The sequence as plain data.

    @param type_name The name of the type, for messages.

    @return The field names.
    """
    if not isinstance(value, list):
        raise SchemaError(f"types.{type_name}.required must be a sequence")

    required_array: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise SchemaError(f"types.{type_name}.required[{index}] must be a string")

        required_array.append(item)

    return tuple(required_array)


def _compile_fields(value: typing.Any, type_name: str) -> dict[str, TypeReference]:
    """
    Compile the named-field map for a mapping type.

    @param value The mapping as plain data.

    @param type_name The name of the type, for messages.

    @return The type of each field.
    """
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
    """
    Compile the allowed string values for an enum type.

    @param value The sequence as plain data.

    @param type_name The name of the type, for messages.

    @return The values allowed.
    """
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
    """
    Compile an optional nested type reference field.

    @param value The mapping that may hold the field.

    @param key The name of the field.

    @param path The path of this part of the schema, for messages.

    @return The reference, or None if the field is absent.
    """
    if key not in value:
        return None

    return _compile_type_reference(value[key], path)


def _compile_type_reference(
    value: typing.Any,
    path: tuple[str | int, ...],
) -> TypeReference:
    """
    Compile a mapping of the form {type: TypeName}.

    @param value The mapping as plain data.

    @param path The path of this part of the schema, for messages.

    @return The reference.
    """
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
    """
    Compile an optional integer scalar from schema builtin text.

    @param value The scalar as plain data, or None if it is absent.

    @param path The path of this part of the schema, for messages.

    @return The integer, or None if it is absent.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise SchemaError(f"{_format_path(path)} must be an integer scalar")

    if not _INTEGER_PATTERN.fullmatch(value):
        raise SchemaError(f"{_format_path(path)} must be an integer scalar")

    try:
        return int(value)
    except ValueError as exc:
        raise SchemaError(
            f"{_format_path(path)} has an integer value too large to convert"
        ) from exc


def _check_reference_exists(
    schema: Schema,
    reference: TypeReference,
    path: tuple[str | int, ...],
) -> None:
    """
    Ensure that a type reference points at a declared schema type.

    @param schema The schema.

    @param reference The reference to check.

    @param path The path of this part of the schema, for messages.
    """
    if reference.name not in schema.types:
        raise SchemaError(f"{_format_path(path)} references unknown type {reference.name!r}")


def _check_type_definition_references(
    schema: Schema,
    type_definition: TypeDefinition,
) -> None:
    """
    Check all nested type references used by a type definition.

    @param schema The schema.

    @param type_definition The type to check.
    """
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
    """
    Check kind-specific invariants within a type definition.

    @param type_definition The type to check.
    """
    if type_definition.kind == "sequence" and type_definition.items is None:
        raise SchemaError(f"types.{type_definition.name}.items is required for sequence types")

    if type_definition.kind == "enum" and not type_definition.enum:
        raise SchemaError(f"types.{type_definition.name}.enum is required for enum types")

    if type_definition.kind == "mapping":
        for required_name in type_definition.required:
            if required_name not in type_definition.fields:
                raise SchemaError(
                    f"types.{type_definition.name}.required contains unknown field "
                    f"{required_name!r}"
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
    walk: _Walk,
) -> list[ValidationError]:
    """
    Dispatch validation for one value against a named schema type.

    @param value The value to validate.

    @param schema The compiled schema.

    @param type_name The name of the type.

    @param path The path of the value, for diagnostics.

    @param walk What validation tracks along the path.

    @return The validation errors, empty if the value is valid.
    """
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

        case "sequence" | "mapping" if isinstance(value, (list, dict)):
            return _validate_collection(value, schema, type_definition, path, walk)

        case "sequence":
            return _validate_sequence(value, schema, type_definition, path, set())

        case "mapping":
            return _validate_mapping(value, schema, type_definition, path, set())

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
    """
    Validate a builtin scalar string against scalar subtype rules.

    @param value The value to validate.

    @param type_definition The type to validate against.

    @param path The path of the value, for diagnostics.

    @return The validation errors, empty if the value is valid.
    """
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
    """
    Validate integer spelling and optional integer range bounds.

    @param value The text of the scalar.

    @param type_definition The type to validate against.

    @param path The path of the value, for diagnostics.

    @return The validation errors, empty if the value is valid.
    """
    if not _INTEGER_PATTERN.fullmatch(value):
        return [
            ValidationError(
                code=ErrorCode.INVALID_SCALAR,
                path=path,
                message=f"expected integer scalar for {type_definition.name}",
            )
        ]

    try:
        integer = int(value)
    except ValueError:
        return [
            ValidationError(
                code=ErrorCode.INVALID_SCALAR,
                path=path,
                message=f"integer scalar for {type_definition.name} is too large to convert",
            )
        ]

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


def _validate_collection(
    value: list[typing.Any] | dict[str, typing.Any],
    schema: Schema,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
    walk: _Walk,
) -> list[ValidationError]:
    """
    Validate a list or dict, refusing deep nesting and cycles first.

    walk.active_id_set holds the containers on the path from the root to
    value; meeting one of them again means the value contains itself. A
    container shared by two branches is not a cycle.

    @param value The list or dict to validate.

    @param schema The compiled schema.

    @param type_definition The type to validate against.

    @param path The path of the value, for diagnostics.

    @param walk What validation tracks along the path.

    @return The validation errors, empty if the value is valid.
    """
    active_id_set = walk.active_id_set

    if korml._limits.is_too_deep(len(active_id_set), walk.max_depth):
        raise InvalidValueError(
            code=ErrorCode.TOO_DEEP,
            path=path,
            message=korml._limits.too_deep_message(walk.max_depth),
        )

    if id(value) in active_id_set:
        raise InvalidValueError(
            code=ErrorCode.CYCLIC_VALUE,
            path=path,
            message="the value contains itself",
        )

    active_id_set.add(id(value))

    try:
        if type_definition.kind == "sequence":
            return _validate_sequence(value, schema, type_definition, path, walk)

        return _validate_mapping(value, schema, type_definition, path, walk)
    finally:
        active_id_set.discard(id(value))


def _validate_sequence(
    value: Builtin,
    schema: Schema,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
    walk: _Walk,
) -> list[ValidationError]:
    """
    Validate a builtin sequence and each item against its item type.

    @param value The value to validate.

    @param schema The compiled schema.

    @param type_definition The type to validate against.

    @param path The path of the value, for diagnostics.

    @param walk What validation tracks along the path.

    @return The validation errors, empty if the value is valid.
    """
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
                walk=walk,
            )
        )

    return error_array


def _validate_mapping(
    value: Builtin,
    schema: Schema,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
    walk: _Walk,
) -> list[ValidationError]:
    """
    Validate a builtin mapping against required, field, and value rules.

    @param value The value to validate.

    @param schema The compiled schema.

    @param type_definition The type to validate against.

    @param path The path of the value, for diagnostics.

    @param walk What validation tracks along the path.

    @return The validation errors, empty if the value is valid.
    """
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
                    unquoted_message="unknown field",
                )
            )
            continue

        error_array.extend(
            _validate_type(
                value=child,
                schema=schema,
                type_name=reference.name,
                path=path + (key,),
                walk=walk,
            )
        )

    return error_array


def _validate_enum(
    value: Builtin,
    type_definition: TypeDefinition,
    path: tuple[str | int, ...],
) -> list[ValidationError]:
    """
    Validate a builtin scalar against an enum value set.

    @param value The value to validate.

    @param type_definition The type to validate against.

    @param path The path of the value, for diagnostics.

    @return The validation errors, empty if the value is valid.
    """
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
            unquoted_message=f"invalid enum value for {type_definition.name}",
        )
    ]


def _construct_type(
    *,
    value: Builtin,
    schema: Schema,
    type_name: str,
    constructor_map: collections.abc.Mapping[str, collections.abc.Callable[..., object]],
) -> object:
    """
    Construct one value by first constructing children, then applying a constructor.

    @param value The validated value.

    @param schema The compiled schema.

    @param type_name The name of the type.

    @param constructor_map The constructor of each type name.

    @return The constructed value.
    """
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
        field_map = {
            key: child for key, child in constructed.items() if key in type_definition.fields
        }

        if type_definition.values is None:
            return constructor(**field_map)

        # Open-ended entries never become keyword arguments; see construct.
        entry_map = {
            key: child for key, child in constructed.items() if key not in type_definition.fields
        }
        return constructor(entry_map, **field_map)

    return constructor(constructed)


def _check_schema_type(schema: Schema) -> None:
    """
    Reject non-v1 schema objects passed into v1 API functions.

    @param schema The object to check.
    """
    if not isinstance(schema, Schema):
        raise TypeError("schema must be a compiled korml.schema.v1.Schema")


def _format_path(path: tuple[str | int, ...]) -> str:
    """
    Format a diagnostic path as compact dotted/indexed text.

    @param path The keys and indices of the path.

    @return The text, or '<root>' for an empty path.
    """
    if not path:
        return "<root>"

    text = str(path[0])

    for part in path[1:]:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}"

    return text
