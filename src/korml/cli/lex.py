# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import argparse
import json

import korml.lexer.v1.file


def run(args: argparse.Namespace) -> None:
    input_text = args.input.read()
    filename = getattr(args.input, "name", "<stdin>")

    file = korml.lexer.v1.file.lex(
        filename=filename,
        input_text=input_text,
    )

    if args.output_format == "json":
        json.dump(
            [token.to_dict() for token in file.token_array],
            args.output,
            indent=2,
        )
        print(file=args.output)
        return

    for token in file.token_array:
        print(f"{token.type.name}\t{token.value!r}", file=args.output)
