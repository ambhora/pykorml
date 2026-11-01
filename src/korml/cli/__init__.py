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
    """
    Add the arguments of the lex subcommand to the parser sp.

    @param sp The parser of the subcommand.
    """
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
        "--dangerous-allow-writing-to-symlink",
        action="store_true",
        help=("If --output is a symbolic link, replace the file it points to instead of refusing"),
    )
    sp.add_argument(
        "--output-format",
        required=False,
        choices=["json", "text"],
        default="json",
    )
    sp.set_defaults(func=korml.cli.lex.run)


def top_level_parser() -> argparse.ArgumentParser:
    """
    Return the argument parser of the korml command line.

    @return The parser, with its subcommands.
    """
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
    """
    Run the korml command line and return its exit status.

    @return 0 on success, 1 for a user error, 130 if interrupted, 70 for an internal failure.
    """
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
    except korml.error.UnsafeOutputError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "  = pass --dangerous-allow-writing-to-symlink to write to its target", file=sys.stderr
        )
        return 1
    except OSError as exc:
        filename = korml.error.escape_controls(str(exc.filename))
        reason = korml.error.escape_controls(str(exc.strerror))
        print(f"error: {filename}: {reason}", file=sys.stderr)
        return 1
    except Exception as exc:
        return handle_uncaught_exception(exc)


def handle_uncaught_exception(exc: Exception) -> int:
    """
    Print the internal failure report for exc and return its exit status.

    @param exc The exception that korml did not expect.

    @return The exit status of an internal failure.
    """
    report = korml.cli.bugreport.render_internal_failure_report(exc=exc, stream=sys.stderr)
    print(report, file=sys.stderr)
    return korml.cli.bugreport.DiagnosticExitCode.INTERNAL_ERROR
