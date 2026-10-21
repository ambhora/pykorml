# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import argparse
import pathlib
import sys

import korml.cli.bugreport
import korml.cli.lex
import korml.error


def first_level_lexer_parser(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--input",
        required=True,
        type=pathlib.Path,
        help="Input korml document",
    )
    sp.add_argument(
        "--output",
        required=False,
        type=pathlib.Path,
        default=None,
        help="Output file; standard output if omitted",
    )
    sp.add_argument(
        "--output-format",
        required=False,
        choices=["json", "text"],
        default="json",
    )
    sp.set_defaults(func=korml.cli.lex.run)


def top_level_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="korml",
        description="korml command line tools",
        epilog="Use 'korml -h' for more information",
    )

    subparser = parser.add_subparsers(title="subcommand", dest="subcommand", required=True)

    lex_sp = subparser.add_parser("lex", help="Lex a korml document and print the tokens")
    first_level_lexer_parser(lex_sp)

    return parser


def main() -> int:
    parser = top_level_parser()
    args = parser.parse_args(None if len(sys.argv) > 1 else ["-h"])

    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("error: interrupted by user", file=sys.stderr)
        return 130
    except korml.error.BugError as exc:
        return handle_uncaught_exception(exc)
    except korml.error.CompilerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        filename = korml.error.escape_controls(str(exc.filename))
        reason = korml.error.escape_controls(str(exc.strerror))
        print(f"error: {filename}: {reason}", file=sys.stderr)
        return 1
    except Exception as exc:
        return handle_uncaught_exception(exc)


def handle_uncaught_exception(exc: Exception) -> int:
    report = korml.cli.bugreport.render_internal_failure_report(exc=exc, stream=sys.stderr)
    print(report, file=sys.stderr)
    return korml.cli.bugreport.DiagnosticExitCode.INTERNAL_ERROR
