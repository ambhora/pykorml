# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import ruamel.yaml

import korml
import testkorml.yamlgen


def test_generated_sources_round_trip_through_loads_and_dumps() -> None:
    for seed in range(100):
        source = testkorml.yamlgen.generate_one(
            testkorml.yamlgen.GenerationConfig(
                seed=seed,
                document_count=1,
                document_end=True,
            )
        )

        stream = korml.loads(source)
        emitted_source = korml.dumps(stream)
        round_tripped_stream = korml.loads(emitted_source)

        assert round_tripped_stream.to_builtin() == stream.to_builtin()


def test_generated_sources_match_ruamel_yaml_builtin_values() -> None:
    yaml = ruamel.yaml.YAML(typ="safe")

    for seed in range(100):
        source = testkorml.yamlgen.generate_one(
            testkorml.yamlgen.GenerationConfig(
                seed=seed,
                document_count=1,
                document_end=True,
            )
        )

        expected = list(yaml.load_all(_without_korml_version_directive(source)))
        actual = korml.loads(source).to_builtin()

        assert actual == expected


def _without_korml_version_directive(source: str) -> str:
    return "\n".join(line for line in source.splitlines() if not line.startswith("%!korml ")) + "\n"
