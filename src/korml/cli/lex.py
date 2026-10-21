# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import argparse
import json
import pathlib
import sys

import korml._atomic
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
        data = sys.stdin.buffer.read()
    else:
        filename = str(input_path)
        data = input_path.read_bytes()

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

    if args.output_format == "json":
        text = json.dumps([token.to_dict() for token in file.token_array], indent=2) + "\n"
    else:
        text = "".join(f"{token.type.name}\t{token.value!r}\n" for token in file.token_array)

    if args.output is None:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.flush()
    else:
        korml._atomic.write_bytes(args.output, text.encode("utf-8"))
