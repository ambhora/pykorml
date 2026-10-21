# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import argparse
import json
import pathlib
import sys

import korml._atomic
import korml._limits
import korml.error
import korml.lexer.file


def run(args: argparse.Namespace) -> None:
    """Lex the input file, or standard input for '-', and print its tokens.

    Korml sources are UTF-8 whatever the locale, so the input is decoded and
    the output encoded as UTF-8; input that is not UTF-8 is a CompilerError.
    """
    input_path: pathlib.Path = args.input

    if str(input_path) == "-":
        filename = "<stdin>"
        data = sys.stdin.buffer.read(korml._limits.MAX_INPUT_BYTES + 1)
    else:
        filename = str(input_path)
        with input_path.open("rb") as stream:
            data = stream.read(korml._limits.MAX_INPUT_BYTES + 1)

    if len(data) > korml._limits.MAX_INPUT_BYTES:
        raise korml.error.CompilerError(
            message=f"input exceeds {korml._limits.MAX_INPUT_BYTES} bytes",
            source_name=filename,
            code="INPUT_TOO_LARGE",
        )

    try:
        # utf-8-sig drops a byte-order mark, as loading does.
        input_text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise korml.error.CompilerError(
            message=f"input is not valid UTF-8 at byte {error.start}",
            source_name=filename,
        ) from error

    file = korml.lexer.file.lex(
        filename=filename,
        input_text=input_text,
    )

    if len(file.token_array) > korml._limits.MAX_TOKENS:
        raise korml.error.CompilerError(
            message=f"token count exceeds {korml._limits.MAX_TOKENS}",
            source_name=filename,
            code="TOO_MANY_TOKENS",
        )

    if args.output_format == "json":
        text = json.dumps([token.to_dict() for token in file.token_array], indent=2) + "\n"
    else:
        text = "".join(f"{token.type.name}\t{token.value!r}\n" for token in file.token_array)

    if args.output is None:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.flush()
    else:
        korml._atomic.write_bytes(args.output, text.encode("utf-8"))
