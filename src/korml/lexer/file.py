# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""Version-dispatching file lexer."""

import korml.core
import korml.error
import korml.lexer.v0.file as lexer_v0_file
import korml.lexer.v1
import korml.lexer.v1.file as lexer_v1_file
import korml.model
from korml.lexer.v1 import File

__all__ = ["detect_version", "lex", "unlex"]


def detect_version(input_text: str) -> korml.model.Version:
    """
    Detect the KORML source version from stream framing.

    The source is v1 if its first line that is not blank (empty, whitespace
    only, or whitespace and a comment) begins with '%!korml' at column 1;
    otherwise it is v0. The v1 lexer then requires that line to be a valid
    directive.

    @param input_text The source text.

    @return Version.v1 or Version.v0.
    """
    line_start = 0

    while line_start < len(input_text):
        line_end = line_start
        while line_end < len(input_text) and input_text[line_end] not in "\r\n":
            line_end += 1

        line_text = input_text[line_start:line_end]
        content = line_text.lstrip(" \t")

        if content == "" or content.startswith("#"):
            line_start = _next_line_start(input_text, line_end)
            continue

        if line_text.startswith("%!korml"):
            return korml.model.Version.v1

        return korml.model.Version.v0

    return korml.model.Version.v0


def lex(
    filename: str,
    input_text: str,
    *,
    version: korml.model.Version | None = None,
    debug: bool = False,
    max_tokens: int | None = None,
) -> File:
    """
    Tokenize a complete KORML source string using the detected or requested version.

    @param filename The name of the source, for diagnostics.

    @param input_text The complete source text.

    @param version The language version, or None to detect it.

    @param debug Whether to trace the lexer on standard error.

    @param max_tokens The largest number of tokens accepted, or None for no limit.

    @return The tokens of the source.
    """
    if version is None:
        version = detect_version(input_text)

    if version is korml.model.Version.v0:
        return lexer_v0_file.lex(
            filename=filename, input_text=input_text, debug=debug, max_tokens=max_tokens
        )

    if version is korml.model.Version.v1:
        return lexer_v1_file.lex(
            filename=filename, input_text=input_text, debug=debug, max_tokens=max_tokens
        )

    raise ValueError(f"unsupported korml version: {version.value!r}")


def unlex(file: File) -> str:
    """
    Convert a tokenized KORML file back to source text.

    @param file The tokenized file.

    @return The source text.
    """
    return "".join(token.value for token in file.token_array)


def _next_line_start(input_text: str, line_end: int) -> int:
    """
    Return the offset of the start of the line after a line that ends at line_end.

    @param input_text The complete source text.

    @param line_end The offset where the line ends.

    @return The offset after the line break, or line_end at the end of the input.
    """
    if line_end < len(input_text) and input_text.startswith("\r\n", line_end):
        return line_end + 2

    if line_end < len(input_text) and input_text[line_end] in "\r\n":
        return line_end + 1

    return line_end
