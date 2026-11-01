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
ValidationError = v1.ValidationError
SchemaError = v1.SchemaError
ConstructionError = v1.ConstructionError
InvalidValueError = v1.InvalidValueError
TypeReference = v1.TypeReference
TypeDefinition = v1.TypeDefinition
Schema = v1.Schema


def compile_schema(
    value: v1.Builtin,
    *,
    version: str = "v1",
) -> Schema:
    """Compile a schema builtin using the selected schema-language version."""
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
    """Validate a builtin value using the selected schema-language version; see v1.validate."""
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
    """Construct user objects using the selected schema-language version; see v1.construct."""
    if version == "v1":
        return v1.construct(value, schema, constructor_map, max_depth=max_depth)

    raise ValueError(f"unsupported korml schema version: {version!r}")
