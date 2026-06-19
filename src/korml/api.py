# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

import pathlib

import korml.emitter.v1
import korml.lexer.v1
import korml.lexer.v1.file
import korml.model
import korml.parser.v1

__all__ = ["dump", "dumps", "load", "loads"]


def loads(
    input_text: str,
    *,
    filename: str = "<string>",
    debug: bool = False,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    file = korml.lexer.v1.file.lex(
        filename=filename,
        input_text=input_text,
        debug=debug,
    )

    if file.version is korml.model.Version.v1:
        return korml.parser.v1.parse(file)

    raise ValueError(f"unsupported korml version: {file.version.value!r}")


def load(
    filename: str | pathlib.Path,
    *,
    debug: bool = False,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    path = pathlib.Path(filename)

    return loads(
        path.read_text(encoding="utf-8"),
        filename=str(path),
        debug=debug,
    )


def dumps(
    value: object,
    *,
    version: korml.model.Version = korml.model.Version.v1,
) -> str:
    if version is korml.model.Version.v1:
        return korml.emitter.v1.emit(_make_stream(value, version=version))

    raise ValueError(f"unsupported korml version: {version.value!r}")


def dump(
    value: object,
    filename: str | pathlib.Path,
    *,
    version: korml.model.Version = korml.model.Version.v1,
) -> None:
    pathlib.Path(filename).write_text(
        dumps(value, version=version),
        encoding="utf-8",
    )


def _make_stream(
    value: object,
    *,
    version: korml.model.Version,
) -> korml.model.Stream[korml.lexer.v1.Token]:
    if isinstance(value, korml.model.Stream):
        return value

    if isinstance(value, korml.model.Value):
        return korml.model.Stream[korml.lexer.v1.Token](
            document_array=[value],
            cst=korml.model.CST(version=version),
        )

    return korml.model.Stream[korml.lexer.v1.Token](
        document_array=[_make_value(value, version=version)],
        cst=korml.model.CST(version=version),
    )


def _make_value(
    value: object,
    *,
    version: korml.model.Version,
) -> korml.model.Value[korml.lexer.v1.Token]:
    if isinstance(value, str):
        return korml.model.Scalar[korml.lexer.v1.Token](
            value,
            cst=korml.model.CST(version=version),
        )

    if isinstance(value, list):
        return korml.model.Sequence[korml.lexer.v1.Token](
            value_array=[_make_value(child, version=version) for child in value],
            cst=korml.model.CST(version=version),
        )

    if isinstance(value, dict):
        mapping = korml.model.Mapping[korml.lexer.v1.Token](
            cst=korml.model.CST(version=version),
        )

        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings")

            mapping.add_item(key, _make_value(child, version=version))

        return mapping

    raise TypeError(f"cannot dump {type(value).__name__!r}")
