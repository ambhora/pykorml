# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Public version-dispatching schema API for KORML."""

import collections.abc
import korml.schema.v1 as v1

__all__ = [
    "v1",
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

ErrorCode = v1.ErrorCode
ValidationError = v1.ValidationError
SchemaError = v1.SchemaError
ConstructionError = v1.ConstructionError
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
    value: v1.Builtin,
    schema: Schema,
    *,
    version: str = "v1",
) -> list[ValidationError]:
    """Validate a builtin value using the selected schema-language version."""
    if version == "v1":
        return v1.validate(value, schema)

    raise ValueError(f"unsupported korml schema version: {version!r}")


def construct(
    value: v1.Builtin,
    schema: Schema,
    constructor_map: collections.abc.Mapping[str, collections.abc.Callable[..., object]] | None = None,
    *,
    version: str = "v1",
) -> object:
    """Construct user objects using the selected schema-language version."""
    if version == "v1":
        return v1.construct(value, schema, constructor_map)

    raise ValueError(f"unsupported korml schema version: {version!r}")
