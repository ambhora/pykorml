# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Mutate generated valid schema documents into expected invalid documents."""

import collections.abc
import copy
import dataclasses
import typing

import korml

import testkorml.schemagen


@dataclasses.dataclass(frozen=True, slots=True)
class MutatedDocument:
    """A mutated document plus the diagnostic it is expected to trigger."""
    name: str
    source: str
    expected_code: korml.schema.ErrorCode
    expected_path: tuple[str | int, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class _MutatedBuiltin:
    """A mutated builtin value plus its expected validation diagnostic."""
    value: dict[str, typing.Any]
    expected_code: korml.schema.ErrorCode
    expected_path: tuple[str | int, ...]


# Mutations are deliberately targeted: each one changes one valid document
# in a way that should trigger a known diagnostic code and path.
def mutate(case: testkorml.schemagen.GeneratedSchemaCase) -> list[MutatedDocument]:
    """Return deterministic invalid-document mutations for a generated schema case."""
    mutation_array: list[MutatedDocument] = []

    _append_if_changed(
        mutation_array,
        "remove-required-root-field",
        case.document_builtin,
        _remove_first_root_required_field(
            document=case.document_builtin,
            schema=case.schema_builtin,
        ),
    )
    _append_if_changed(
        mutation_array,
        "add-unknown-root-field",
        case.document_builtin,
        _add_unknown_root_field(case.document_builtin),
    )
    _append_if_changed(
        mutation_array,
        "replace-first-scalar-with-sequence",
        case.document_builtin,
        _replace_first_kind(
            document=case.document_builtin,
            schema=case.schema_builtin,
            kind="scalar",
            replacement_factory=lambda value: [value],
            expected_code=korml.schema.ErrorCode.WRONG_KIND,
        ),
    )
    _append_if_changed(
        mutation_array,
        "replace-first-sequence-with-scalar",
        case.document_builtin,
        _replace_first_kind(
            document=case.document_builtin,
            schema=case.schema_builtin,
            kind="sequence",
            replacement_factory=lambda value: "not_a_sequence",
            expected_code=korml.schema.ErrorCode.WRONG_KIND,
        ),
    )
    _append_if_changed(
        mutation_array,
        "replace-first-integer-with-invalid-scalar",
        case.document_builtin,
        _replace_first_schema_scalar(
            document=case.document_builtin,
            schema=case.schema_builtin,
            scalar="integer",
            replacement="not_an_integer",
            expected_code=korml.schema.ErrorCode.INVALID_SCALAR,
        ),
    )
    _append_if_changed(
        mutation_array,
        "replace-first-boolean-with-invalid-scalar",
        case.document_builtin,
        _replace_first_schema_scalar(
            document=case.document_builtin,
            schema=case.schema_builtin,
            scalar="boolean",
            replacement="maybe",
            expected_code=korml.schema.ErrorCode.INVALID_SCALAR,
        ),
    )
    _append_if_changed(
        mutation_array,
        "replace-first-enum-with-invalid-scalar",
        case.document_builtin,
        _replace_first_enum(
            document=case.document_builtin,
            schema=case.schema_builtin,
            replacement="invalid_enum_value",
        ),
    )

    return mutation_array


# Some generated schemas do not contain every possible kind. Optional
# mutations are skipped when there is no matching target to change.
def _append_if_changed(
    mutation_array: list[MutatedDocument],
    name: str,
    original: dict[str, typing.Any],
    mutation: _MutatedBuiltin | None,
) -> None:
    """Append a mutation only when it exists and changes the original document."""
    if mutation is None:
        return

    if mutation.value == original:
        return

    mutation_array.append(
        MutatedDocument(
            name=name,
            source=korml.dumps(mutation.value),
            expected_code=mutation.expected_code,
            expected_path=mutation.expected_path,
        )
    )


def _remove_first_root_required_field(
    *,
    document: dict[str, typing.Any],
    schema: dict[str, typing.Any],
) -> _MutatedBuiltin | None:
    """Remove the first present required root field."""
    root_type = schema["root"]["type"]
    root_definition = schema["types"][root_type]
    required_array = root_definition.get("required", [])

    for field_name in required_array:
        if field_name in document:
            mutated = copy.deepcopy(document)
            del mutated[field_name]
            return _MutatedBuiltin(
                value=mutated,
                expected_code=korml.schema.ErrorCode.MISSING_FIELD,
                expected_path=(field_name,),
            )

    return None


def _add_unknown_root_field(document: dict[str, typing.Any]) -> _MutatedBuiltin:
    """Add a root field that the generated schema does not define."""
    field_name = "unknown_generated_field"
    mutated = copy.deepcopy(document)
    mutated[field_name] = "value"
    return _MutatedBuiltin(
        value=mutated,
        expected_code=korml.schema.ErrorCode.UNKNOWN_FIELD,
        expected_path=(field_name,),
    )


def _replace_first_kind(
    *,
    document: dict[str, typing.Any],
    schema: dict[str, typing.Any],
    kind: str,
    replacement_factory: collections.abc.Callable[[typing.Any], typing.Any],
    expected_code: korml.schema.ErrorCode,
) -> _MutatedBuiltin | None:
    """Replace the first value whose schema type has the requested kind."""
    mutated = copy.deepcopy(document)
    root_type = schema["root"]["type"]
    path = _replace_first_kind_in_place(
        value=mutated,
        schema=schema,
        type_name=root_type,
        kind=kind,
        replacement_factory=replacement_factory,
        path=(),
    )

    if path is None:
        return None

    return _MutatedBuiltin(
        value=mutated,
        expected_code=expected_code,
        expected_path=path,
    )


def _replace_first_kind_in_place(
    *,
    value: typing.Any,
    schema: dict[str, typing.Any],
    type_name: str,
    kind: str,
    replacement_factory: collections.abc.Callable[[typing.Any], typing.Any],
    path: tuple[str | int, ...],
) -> tuple[str | int, ...] | None:
    """Recursively locate and replace the first value of a requested kind."""
    type_definition = schema["types"][type_name]
    type_kind = type_definition["kind"]

    if type_kind == kind:
        return path

    # For mappings, field-specific references win; dynamic values are used
    # only when the concrete key is not listed in fields.
    if type_kind == "mapping" and isinstance(value, dict):
        for key, child in value.items():
            reference = type_definition.get("fields", {}).get(key) or type_definition.get("values")

            if reference is None:
                continue

            child_type_name = reference["type"]
            child_type_definition = schema["types"][child_type_name]
            child_path = path + (key,)

            if child_type_definition["kind"] == kind:
                value[key] = replacement_factory(child)
                return child_path

            replaced_path = _replace_first_kind_in_place(
                value=child,
                schema=schema,
                type_name=child_type_name,
                kind=kind,
                replacement_factory=replacement_factory,
                path=child_path,
            )
            if replaced_path is not None:
                return replaced_path

    if type_kind == "sequence" and isinstance(value, list):
        item_type_name = type_definition["items"]["type"]
        item_type_definition = schema["types"][item_type_name]

        for index, child in enumerate(value):
            child_path = path + (index,)

            if item_type_definition["kind"] == kind:
                value[index] = replacement_factory(child)
                return child_path

            replaced_path = _replace_first_kind_in_place(
                value=child,
                schema=schema,
                type_name=item_type_name,
                kind=kind,
                replacement_factory=replacement_factory,
                path=child_path,
            )
            if replaced_path is not None:
                return replaced_path

    return None


def _replace_first_schema_scalar(
    *,
    document: dict[str, typing.Any],
    schema: dict[str, typing.Any],
    scalar: str,
    replacement: str,
    expected_code: korml.schema.ErrorCode,
) -> _MutatedBuiltin | None:
    """Replace the first scalar value with a requested scalar subtype."""
    mutated = copy.deepcopy(document)
    root_type = schema["root"]["type"]
    path = _replace_first_schema_scalar_in_place(
        value=mutated,
        schema=schema,
        type_name=root_type,
        scalar=scalar,
        replacement=replacement,
        path=(),
    )

    if path is None:
        return None

    return _MutatedBuiltin(
        value=mutated,
        expected_code=expected_code,
        expected_path=path,
    )


def _replace_first_schema_scalar_in_place(
    *,
    value: typing.Any,
    schema: dict[str, typing.Any],
    type_name: str,
    scalar: str,
    replacement: str,
    path: tuple[str | int, ...],
) -> tuple[str | int, ...] | None:
    """Recursively locate and replace the first scalar subtype value."""
    type_definition = schema["types"][type_name]
    kind = type_definition["kind"]

    # Scalar subtype mutations follow the same traversal order as validation
    # so the expected diagnostic path is stable.
    if kind == "mapping" and isinstance(value, dict):
        for key, child in value.items():
            reference = type_definition.get("fields", {}).get(key) or type_definition.get("values")

            if reference is None:
                continue

            child_type_name = reference["type"]
            child_type_definition = schema["types"][child_type_name]
            child_path = path + (key,)

            if child_type_definition["kind"] == "scalar":
                if child_type_definition.get("scalar", "string") == scalar:
                    value[key] = replacement
                    return child_path

            replaced_path = _replace_first_schema_scalar_in_place(
                value=child,
                schema=schema,
                type_name=child_type_name,
                scalar=scalar,
                replacement=replacement,
                path=child_path,
            )
            if replaced_path is not None:
                return replaced_path

    if kind == "sequence" and isinstance(value, list):
        item_type_name = type_definition["items"]["type"]
        item_type_definition = schema["types"][item_type_name]

        for index, child in enumerate(value):
            child_path = path + (index,)

            if item_type_definition["kind"] == "scalar":
                if item_type_definition.get("scalar", "string") == scalar:
                    value[index] = replacement
                    return child_path

            replaced_path = _replace_first_schema_scalar_in_place(
                value=child,
                schema=schema,
                type_name=item_type_name,
                scalar=scalar,
                replacement=replacement,
                path=child_path,
            )
            if replaced_path is not None:
                return replaced_path

    return None


def _replace_first_enum(
    *,
    document: dict[str, typing.Any],
    schema: dict[str, typing.Any],
    replacement: str,
) -> _MutatedBuiltin | None:
    """Replace the first enum value with an invalid enum string."""
    mutated = copy.deepcopy(document)
    root_type = schema["root"]["type"]
    path = _replace_first_enum_in_place(
        value=mutated,
        schema=schema,
        type_name=root_type,
        replacement=replacement,
        path=(),
    )

    if path is None:
        return None

    return _MutatedBuiltin(
        value=mutated,
        expected_code=korml.schema.ErrorCode.INVALID_ENUM_VALUE,
        expected_path=path,
    )


def _replace_first_enum_in_place(
    *,
    value: typing.Any,
    schema: dict[str, typing.Any],
    type_name: str,
    replacement: str,
    path: tuple[str | int, ...],
) -> tuple[str | int, ...] | None:
    """Recursively locate and replace the first enum value."""
    type_definition = schema["types"][type_name]
    kind = type_definition["kind"]

    if kind == "mapping" and isinstance(value, dict):
        for key, child in value.items():
            reference = type_definition.get("fields", {}).get(key) or type_definition.get("values")

            if reference is None:
                continue

            child_type_name = reference["type"]
            child_type_definition = schema["types"][child_type_name]
            child_path = path + (key,)

            if child_type_definition["kind"] == "enum":
                value[key] = replacement
                return child_path

            replaced_path = _replace_first_enum_in_place(
                value=child,
                schema=schema,
                type_name=child_type_name,
                replacement=replacement,
                path=child_path,
            )
            if replaced_path is not None:
                return replaced_path

    if kind == "sequence" and isinstance(value, list):
        item_type_name = type_definition["items"]["type"]
        item_type_definition = schema["types"][item_type_name]

        for index, child in enumerate(value):
            child_path = path + (index,)

            if item_type_definition["kind"] == "enum":
                value[index] = replacement
                return child_path

            replaced_path = _replace_first_enum_in_place(
                value=child,
                schema=schema,
                type_name=item_type_name,
                replacement=replacement,
                path=child_path,
            )
            if replaced_path is not None:
                return replaced_path

    return None
