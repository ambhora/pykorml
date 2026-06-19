# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import dataclasses

import pytest

import korml


# Minimal schema used to verify the public version-dispatching API.
SCHEMA_SOURCE = """%!korml version 1.0
---
schema: korml.schema.v1
root:
  type: Root
types:
  String:
    kind: scalar
  Integer:
    kind: scalar
    scalar: integer
  Root:
    kind: mapping
    required:
      - name
      - count
    fields:
      name:
        type: String
      count:
        type: Integer
...
"""


# The committed public API re-exports the current v1 implementation types
# while keeping the implementation in the versioned namespace.
def test_schema_api_exposes_v1_objects() -> None:
    assert korml.schema.ErrorCode is korml.schema.v1.ErrorCode
    assert korml.schema.ValidationError is korml.schema.v1.ValidationError
    assert korml.schema.SchemaError is korml.schema.v1.SchemaError
    assert korml.schema.ConstructionError is korml.schema.v1.ConstructionError
    assert korml.schema.TypeReference is korml.schema.v1.TypeReference
    assert korml.schema.TypeDefinition is korml.schema.v1.TypeDefinition
    assert korml.schema.Schema is korml.schema.v1.Schema


# Omitting version should route through v1 today. Future versions can be
# added by extending the dispatcher without changing this call shape.
def test_schema_api_compiles_and_validates_with_default_version() -> None:
    schema = korml.schema.compile_schema(korml.loads(SCHEMA_SOURCE).to_builtin()[0])
    document = korml.loads(
        """%!korml version 1.0
---
name: demo
count: 12
...
"""
    ).to_builtin()[0]

    assert korml.schema.validate(document, schema) == []


def test_schema_api_accepts_explicit_v1_version() -> None:
    schema = korml.schema.compile_schema(
        korml.loads(SCHEMA_SOURCE).to_builtin()[0],
        version="v1",
    )
    document = korml.loads(
        """%!korml version 1.0
---
name: demo
count: 12
...
"""
    ).to_builtin()[0]

    assert korml.schema.validate(document, schema, version="v1") == []


# Unknown versions are rejected explicitly instead of silently falling back.
def test_schema_api_rejects_unknown_future_version() -> None:
    schema_builtin = korml.loads(SCHEMA_SOURCE).to_builtin()[0]

    with pytest.raises(ValueError, match="unsupported korml schema version"):
        korml.schema.compile_schema(schema_builtin, version="v2")


# Construction tests verify that schema type names can be mapped to user
# constructors while KORML builtins remain plain strings/lists/dicts.
@dataclasses.dataclass(frozen=True, slots=True)
class Root:
    name: str
    count: int


def test_schema_api_constructs_with_default_version() -> None:
    schema = korml.schema.compile_schema(korml.loads(SCHEMA_SOURCE).to_builtin()[0])
    document = korml.loads(
        """%!korml version 1.0
---
name: demo
count: 12
...
"""
    ).to_builtin()[0]

    value = korml.schema.construct(
        document,
        schema,
        {
            "Integer": int,
            "Root": Root,
        },
    )

    assert value == Root(
        name="demo",
        count=12,
    )
