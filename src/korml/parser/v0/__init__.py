# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""KORML v0 parser.

v0 has a single implicit document, so parsing applies the v1 document-body
parser to the whole token stream instead of splitting on document markers.
"""

from korml.lexer import v0 as lexer_v0
import korml.model
import korml.parser.v1 as parser_v1

ErrorCode = parser_v1.ErrorCode

__all__ = ["ErrorCode", "parse"]


def parse(file: lexer_v0.File) -> korml.model.Stream[lexer_v0.Token]:
    """Parse a tokenized KORML v0 file into a one-document stream."""
    if file.version is not korml.model.Version.v0:
        raise ValueError(f"parser v0 cannot parse version {file.version.value!r}")

    document_array: list[korml.model.Value[lexer_v0.Token]] = []

    if parser_v1._first_non_trivia(file.token_array) is not None:
        document_array.append(
            parser_v1._parse_value(
                file.token_array,
                version=file.version,
                source_name=file.filename,
            )
        )

    return korml.model.Stream[lexer_v0.Token](
        document_array=document_array,
        filename=file.filename,
        cst=korml.model.CST(
            version=file.version,
            token_array=file.token_array,
        ),
    )
