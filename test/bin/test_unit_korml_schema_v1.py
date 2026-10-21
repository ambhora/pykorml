# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import dataclasses

import pytest

import korml

# Shared schema used by most validator and constructor tests.
# It exercises nested mappings, sequences, dynamic mapping values, enums,
# booleans, arbitrary-length integers, and a fixed-width integer type.
BASE_SCHEMA_SOURCE = """%!korml version 1.0
---
schema: korml.schema.v1
root:
  type: ProjectConfig
types:
  String:
    kind: scalar
  Integer:
    kind: scalar
    scalar: integer
  Boolean:
    kind: scalar
    scalar: boolean
  Integer64:
    kind: scalar
    scalar: integer
    minimum: -9223372036854775808
    maximum: 9223372036854775807
  BuildMode:
    kind: enum
    enum:
      - debug
      - release
  SimulationConfig:
    kind: mapping
    required:
      - name
      - count
      - enabled
    fields:
      name:
        type: String
      count:
        type: Integer
      enabled:
        type: Boolean
      workers:
        type: Integer64
  SimulationList:
    kind: sequence
    items:
      type: SimulationConfig
  Environment:
    kind: mapping
    values:
      type: String
  ProjectConfig:
    kind: mapping
    required:
      - project_name
      - default_simulation
      - simulations
      - mode
    fields:
      project_name:
        type: String
      default_simulation:
        type: SimulationConfig
      simulations:
        type: SimulationList
      environment:
        type: Environment
      mode:
        type: BuildMode
...
"""


# Test helpers intentionally go through loads().to_builtin(), because the
# schema layer consumes KORML builtins rather than parser CST objects.
def _compile(source: str = BASE_SCHEMA_SOURCE) -> korml.schema.Schema:
    return korml.schema.v1.compile_schema(korml.loads(source).to_builtin()[0])


def _load_document(source: str) -> object:
    return korml.loads(source).to_builtin()[0]


# Schema compilation rejects malformed schema specifications before any
# user document is validated against them.
def test_compile_schema_requires_mapping_document() -> None:
    with pytest.raises(korml.schema.SchemaError, match="schema document must be a mapping"):
        korml.schema.v1.compile_schema("not-a-mapping")


def test_compile_schema_requires_schema_field() -> None:
    with pytest.raises(korml.schema.SchemaError, match="schema field"):
        korml.schema.v1.compile_schema(
            {
                "root": {"type": "Root"},
                "types": {},
            }
        )


def test_compile_schema_requires_root() -> None:
    with pytest.raises(korml.schema.SchemaError, match="root"):
        korml.schema.v1.compile_schema(
            {
                "schema": "korml.schema.v1",
                "types": {},
            }
        )


def test_compile_schema_requires_types() -> None:
    with pytest.raises(korml.schema.SchemaError, match="types"):
        korml.schema.v1.compile_schema(
            {
                "schema": "korml.schema.v1",
                "root": {"type": "Root"},
            }
        )


def test_compile_schema_rejects_unknown_root_type() -> None:
    with pytest.raises(korml.schema.SchemaError, match="unknown type"):
        korml.schema.v1.compile_schema(
            {
                "schema": "korml.schema.v1",
                "root": {"type": "Root"},
                "types": {},
            }
        )


def test_compile_schema_rejects_unknown_field_type() -> None:
    with pytest.raises(korml.schema.SchemaError, match="unknown type"):
        korml.schema.v1.compile_schema(
            {
                "schema": "korml.schema.v1",
                "root": {"type": "Root"},
                "types": {
                    "Root": {
                        "kind": "mapping",
                        "fields": {
                            "value": {"type": "Missing"},
                        },
                    }
                },
            }
        )


def test_compile_schema_rejects_required_field_not_in_fields() -> None:
    with pytest.raises(korml.schema.SchemaError, match="required"):
        korml.schema.v1.compile_schema(
            {
                "schema": "korml.schema.v1",
                "root": {"type": "Root"},
                "types": {
                    "Root": {
                        "kind": "mapping",
                        "required": ["missing"],
                        "fields": {},
                    }
                },
            }
        )


# Validation walks the complete builtin tree and resolves each nested field
# through the named type registry declared by the schema.
def test_validate_accepts_nested_valid_document() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
default_simulation:
  name: baseline
  count: 4
  enabled: true
  workers: 9223372036854775807
simulations:
  - name: small
    count: 1
    enabled: false
  - name: large
    count: 16
    enabled: true
environment:
  CC: gcc
  CXX: g++
mode: debug
...
"""
    )

    assert korml.schema.v1.validate(document, schema) == []


# The following tests check stable diagnostic codes instead of error text.
# Error text may be improved later without changing the diagnostic API.
def test_validate_rejects_missing_required_field() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
simulations: []
mode: debug
...
"""
    )

    error_array = korml.schema.v1.validate(document, schema)

    assert error_array
    assert error_array[0].code is korml.schema.ErrorCode.MISSING_FIELD


def test_validate_rejects_unknown_field_without_values() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
unknown: value
default_simulation:
  name: baseline
  count: 4
  enabled: true
simulations: []
mode: debug
...
"""
    )

    error_array = korml.schema.v1.validate(document, schema)

    assert any(error.code is korml.schema.ErrorCode.UNKNOWN_FIELD for error in error_array)


def test_validate_accepts_dynamic_mapping_values() -> None:
    schema = _compile(
        """%!korml version 1.0
---
schema: korml.schema.v1
root:
  type: Environment
types:
  String:
    kind: scalar
  Environment:
    kind: mapping
    values:
      type: String
...
"""
    )

    assert korml.schema.v1.validate({"CC": "gcc", "CXX": "g++"}, schema) == []


def test_validate_rejects_invalid_integer() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
default_simulation:
  name: baseline
  count: four
  enabled: true
simulations: []
mode: debug
...
"""
    )

    error_array = korml.schema.v1.validate(document, schema)

    assert any(error.code is korml.schema.ErrorCode.INVALID_SCALAR for error in error_array)


def test_validate_rejects_integer64_out_of_range() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
default_simulation:
  name: baseline
  count: 4
  enabled: true
  workers: 9223372036854775808
simulations: []
mode: debug
...
"""
    )

    error_array = korml.schema.v1.validate(document, schema)

    assert any(error.code is korml.schema.ErrorCode.OUT_OF_RANGE for error in error_array)


def test_validate_rejects_invalid_boolean() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
default_simulation:
  name: baseline
  count: 4
  enabled: maybe
simulations: []
mode: debug
...
"""
    )

    error_array = korml.schema.v1.validate(document, schema)

    assert any(error.code is korml.schema.ErrorCode.INVALID_SCALAR for error in error_array)


def test_validate_rejects_invalid_enum() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
default_simulation:
  name: baseline
  count: 4
  enabled: true
simulations: []
mode: fast
...
"""
    )

    error_array = korml.schema.v1.validate(document, schema)

    assert any(error.code is korml.schema.ErrorCode.INVALID_ENUM_VALUE for error in error_array)


# Constructor tests use small dataclasses as stand-ins for user-defined
# host-language types mapped from schema type names.
@dataclasses.dataclass(frozen=True, slots=True)
class SimulationConfig:
    name: str
    count: int
    enabled: bool
    workers: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ProjectConfig:
    project_name: str
    default_simulation: SimulationConfig
    simulations: list[SimulationConfig]
    mode: str
    environment: dict[str, str] | None = None


def _parse_bool(value: str) -> bool:
    if value == "true":
        return True

    if value == "false":
        return False

    raise ValueError(f"invalid boolean value {value!r}")


# Construction first validates the builtin value, then constructs child
# values before invoking the parent mapping constructor with keywords.
def test_construct_builds_nested_dataclasses() -> None:
    schema = _compile()
    document = _load_document(
        """%!korml version 1.0
---
project_name: demo
default_simulation:
  name: baseline
  count: 4
  enabled: true
simulations:
  - name: small
    count: 1
    enabled: false
environment:
  CC: gcc
mode: release
...
"""
    )

    value = korml.schema.v1.construct(
        document,
        schema,
        {
            "Integer": int,
            "Integer64": int,
            "Boolean": _parse_bool,
            "SimulationConfig": SimulationConfig,
            "ProjectConfig": ProjectConfig,
        },
    )

    assert value == ProjectConfig(
        project_name="demo",
        default_simulation=SimulationConfig(
            name="baseline",
            count=4,
            enabled=True,
        ),
        simulations=[
            SimulationConfig(
                name="small",
                count=1,
                enabled=False,
            )
        ],
        environment={"CC": "gcc"},
        mode="release",
    )


def test_construct_raises_construction_error_on_invalid_document() -> None:
    schema = _compile()

    with pytest.raises(korml.schema.ConstructionError) as error_info:
        korml.schema.v1.construct(
            {
                "project_name": "demo",
                "mode": "debug",
            },
            schema,
        )

    assert error_info.value.error_array


# The checked-in schema specification is itself a KORML schema document, so
# it should validate against the schema language it defines.
def test_schema_specification_validates_itself() -> None:
    schema_builtin = korml.load("share/korml/schema/v1/schema.korml").to_builtin()[0]
    schema = korml.schema.compile_schema(schema_builtin)

    assert korml.schema.validate(schema_builtin, schema) == []


def test_schema_oversized_integer_bound_is_a_schema_error() -> None:
    with pytest.raises(korml.schema.SchemaError, match="integer value too large"):
        korml.schema.v1._compile_optional_integer("9" * 4301, ("minimum",))


def test_oversized_integer_value_returns_validation_error() -> None:
    integer_type = korml.schema.v1.TypeDefinition(name="Integer", kind="scalar", scalar="integer")

    errors = korml.schema.v1._validate_integer_scalar("9" * 4301, integer_type, ("value",))

    assert len(errors) == 1
    assert errors[0].code is korml.schema.ErrorCode.INVALID_SCALAR
    assert errors[0].path == ("value",)
