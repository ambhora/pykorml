# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

import ruamel.yaml
import testkorml.yamlgen

import korml


def test_generated_v0_sources_match_ruamel_yaml_builtin_values() -> None:
    yaml = ruamel.yaml.YAML(typ="safe")

    for seed in range(100):
        source = _to_v0_source(
            testkorml.yamlgen.generate_one(
                testkorml.yamlgen.GenerationConfig(
                    seed=seed,
                    document_count=1,
                    document_end=True,
                )
            )
        )

        assert korml.loads(source).version is korml.Version.v0
        assert korml.loads(source).to_builtin() == [yaml.load(source)]


def test_generated_v0_sources_round_trip_through_dumps() -> None:
    for seed in range(100):
        source = _to_v0_source(
            testkorml.yamlgen.generate_one(
                testkorml.yamlgen.GenerationConfig(
                    seed=seed,
                    document_count=1,
                    document_end=True,
                )
            )
        )

        stream = korml.loads(source)
        emitted_source = korml.dumps(stream.to_builtin()[0], version=korml.Version.v0)
        round_tripped_stream = korml.loads(emitted_source)

        assert round_tripped_stream.version is korml.Version.v0
        assert round_tripped_stream.to_builtin() == stream.to_builtin()


def _to_v0_source(source: str) -> str:
    return (
        "\n".join(
            line
            for line in source.splitlines()
            if not line.startswith("%!korml ") and line not in {"---", "..."}
        )
        + "\n"
    )
