# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Public version-dispatching schema API for KORML."""

import collections.abc

import korml._limits
import korml.schema.v1 as v1

__all__ = [
    "v1",
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

ErrorCode = v1.ErrorCode
"""The stable diagnostic codes; see korml.schema.v1.ErrorCode."""
ValidationError = v1.ValidationError
"""A schema diagnostic; see korml.schema.v1.ValidationError."""
SchemaError = v1.SchemaError
"""A malformed schema; see korml.schema.v1.SchemaError."""
ConstructionError = v1.ConstructionError
"""A failed construction; see korml.schema.v1.ConstructionError."""
InvalidValueError = v1.InvalidValueError
"""A value that cannot be validated; see korml.schema.v1.InvalidValueError."""
TypeReference = v1.TypeReference
"""A reference to a named type; see korml.schema.v1.TypeReference."""
TypeDefinition = v1.TypeDefinition
"""A compiled named type; see korml.schema.v1.TypeDefinition."""
Schema = v1.Schema
"""A compiled schema; see korml.schema.v1.Schema."""


def compile_schema(
    value: v1.Builtin,
    *,
    version: str = "v1",
) -> Schema:
    """
    Compile a schema builtin using the selected schema-language version.

    @param value The schema document as plain data.

    @param version The schema language version; only 'v1' exists.

    @return The schema.
    """
    if version == "v1":
        return v1.compile_schema(value)

    raise ValueError(f"unsupported korml schema version: {version!r}")


def validate(
    value: v1.Builtin | None,
    schema: Schema,
    *,
    version: str = "v1",
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> list[ValidationError]:
    """
    Validate a builtin value using the selected schema-language version; see v1.validate.

    @param value The plain data, or None for an empty document.

    @param schema The compiled schema.

    @param version The schema language version; only 'v1' exists.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The validation errors, empty if the value is valid.
    """
    if version == "v1":
        return v1.validate(value, schema, max_depth=max_depth)

    raise ValueError(f"unsupported korml schema version: {version!r}")


def construct(
    value: v1.Builtin | None,
    schema: Schema,
    constructor_map: collections.abc.Mapping[str, collections.abc.Callable[..., object]]
    | None = None,
    *,
    version: str = "v1",
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> object:
    """
    Construct user objects using the selected schema-language version; see v1.construct.

    @param value The plain data, or None for an empty document.

    @param schema The compiled schema.

    @param constructor_map The constructor of each type name, or None for none.

    @param version The schema language version; only 'v1' exists.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The constructed value.
    """
    if version == "v1":
        return v1.construct(value, schema, constructor_map, max_depth=max_depth)

    raise ValueError(f"unsupported korml schema version: {version!r}")
