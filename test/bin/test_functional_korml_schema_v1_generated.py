# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import testkorml.schemagen
import testkorml.schemamutation

import korml


# Generated cases pair a schema with a document built from that exact schema,
# so every generated document should validate without diagnostics.
def test_generated_valid_documents_validate() -> None:
    for seed in range(100):
        case = testkorml.schemagen.generate_one(seed)
        schema = korml.schema.compile_schema(
            korml.loads(case.schema_source).to_builtin()[0],
        )
        document = korml.loads(case.document_source).to_builtin()[0]

        assert korml.schema.validate(document, schema) == []


# Invalid generated documents are derived by targeted mutations. Each
# mutation declares the diagnostic code/path that must appear in the result.
def test_generated_invalid_documents_do_not_validate() -> None:
    for seed in range(100):
        case = testkorml.schemagen.generate_one(seed)
        schema = korml.schema.compile_schema(
            korml.loads(case.schema_source).to_builtin()[0],
        )

        mutation_array = testkorml.schemamutation.mutate(case)

        assert mutation_array

        for mutation in mutation_array:
            document = korml.loads(mutation.source).to_builtin()[0]
            error_array = korml.schema.validate(document, schema)

            assert error_array, mutation.name
            assert any(
                error.code == mutation.expected_code and error.path == mutation.expected_path
                for error in error_array
            ), (
                mutation.name,
                mutation.expected_code,
                mutation.expected_path,
                error_array,
            )
