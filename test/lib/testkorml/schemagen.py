# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Generate schema/document pairs for functional schema validation tests."""

import dataclasses
import random
import typing

import korml


@dataclasses.dataclass(frozen=True, slots=True)
class GeneratedSchemaCase:
    """A generated schema source together with one valid document for it."""

    schema_source: str
    document_source: str
    schema_builtin: dict[str, typing.Any]
    document_builtin: dict[str, typing.Any]


@dataclasses.dataclass(slots=True)
class _GenerationState:
    """Mutable random-generation state shared across recursive schema generation."""

    rng: random.Random
    next_type_index: int = 0

    def next_type_name(self, prefix: str) -> str:
        """Return a fresh generated type name with the requested prefix."""
        self.next_type_index += 1
        return f"{prefix}{self.next_type_index}"


# Keep the generated language subset small and deterministic: a root mapping
# contains required fields whose values may recursively be leaves, sequences,
# or nested mappings.
def generate_one(seed: int | None = None) -> GeneratedSchemaCase:
    """Generate one schema and one valid document accepted by that schema."""
    state = _GenerationState(rng=random.Random(seed))

    # Prelude-like types are included in every generated schema so nested
    # generated types can reference stable scalar and enum definitions.
    type_map: dict[str, typing.Any] = {
        "String": {
            "kind": "scalar",
        },
        "Integer": {
            "kind": "scalar",
            "scalar": "integer",
        },
        "Boolean": {
            "kind": "scalar",
            "scalar": "boolean",
        },
        "SmallInteger": {
            "kind": "scalar",
            "scalar": "integer",
            "minimum": "-10",
            "maximum": "10",
        },
        "BuildMode": {
            "kind": "enum",
            "enum": ["debug", "release"],
        },
    }

    root_value = _generate_mapping_type(
        state=state,
        type_map=type_map,
        type_name="Root",
        depth=0,
    )

    schema_builtin = {
        "schema": "korml.schema.v1",
        "root": {
            "type": "Root",
        },
        "types": type_map,
    }

    return GeneratedSchemaCase(
        schema_source=korml.dumps(schema_builtin),
        document_source=korml.dumps(root_value),
        schema_builtin=schema_builtin,
        document_builtin=root_value,
    )


def _generate_mapping_type(
    *,
    state: _GenerationState,
    type_map: dict[str, typing.Any],
    type_name: str,
    depth: int,
) -> dict[str, typing.Any]:
    """Generate a mapping type and its matching valid builtin value."""
    field_count = state.rng.randint(2, 4)
    field_map: dict[str, typing.Any] = {}
    required_array: list[str] = []
    value_map: dict[str, typing.Any] = {}

    for field_index in range(field_count):
        field_name = f"field_{depth}_{field_index}"
        child_type_name, child_value = _generate_type_and_value(
            state=state,
            type_map=type_map,
            depth=depth + 1,
        )

        field_map[field_name] = {
            "type": child_type_name,
        }
        required_array.append(field_name)
        value_map[field_name] = child_value

    type_map[type_name] = {
        "kind": "mapping",
        "required": required_array,
        "fields": field_map,
    }

    return value_map


def _generate_type_and_value(
    *,
    state: _GenerationState,
    type_map: dict[str, typing.Any],
    depth: int,
) -> tuple[str, typing.Any]:
    """Generate a nested type name and a builtin value valid for that type."""
    # Bound recursion depth so generated schemas stay readable and tests run
    # quickly while still exercising nested construction paths.
    if depth >= 3:
        return _generate_leaf_type_and_value(state)

    kind = state.rng.choice(["leaf", "leaf", "sequence", "mapping"])

    if kind == "leaf":
        return _generate_leaf_type_and_value(state)

    if kind == "sequence":
        item_type_name, first_value = _generate_type_and_value(
            state=state,
            type_map=type_map,
            depth=depth + 1,
        )
        type_name = state.next_type_name("Sequence")
        type_map[type_name] = {
            "kind": "sequence",
            "items": {
                "type": item_type_name,
            },
        }
        return type_name, [first_value, first_value]

    type_name = state.next_type_name("Mapping")
    value = _generate_mapping_type(
        state=state,
        type_map=type_map,
        type_name=type_name,
        depth=depth,
    )
    return type_name, value


def _generate_leaf_type_and_value(state: _GenerationState) -> tuple[str, str]:
    """Generate a scalar or enum leaf type reference and valid scalar text."""
    type_name = state.rng.choice(["String", "Integer", "Boolean", "SmallInteger", "BuildMode"])

    if type_name == "String":
        return type_name, f"value_{state.next_type_index}"

    if type_name == "Integer":
        return type_name, str(state.rng.randint(-100000, 100000))

    if type_name == "SmallInteger":
        return type_name, str(state.rng.randint(-10, 10))

    if type_name == "Boolean":
        return type_name, state.rng.choice(["true", "false"])

    if type_name == "BuildMode":
        return type_name, state.rng.choice(["debug", "release"])

    raise AssertionError(f"unsupported generated leaf type {type_name!r}")
