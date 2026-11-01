# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""KORML v0 parser.

v0 has a single implicit document, so parsing applies the v1 document-body
parser to the whole token stream instead of splitting on document markers.
"""

import korml._limits
import korml.model
import korml.parser.v1 as parser_v1
from korml.lexer import v0 as lexer_v0

ErrorCode = parser_v1.ErrorCode
"""The codes of the errors the parser reports, shared with v1."""

__all__ = ["ErrorCode", "parse"]


def parse(
    file: lexer_v0.File,
    *,
    max_tokens: int | None = korml._limits.MAX_TOKENS,
    max_work: int | None = korml._limits.MAX_PARSE_WORK,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
) -> korml.model.Stream[lexer_v0.Token]:
    """
    Parse a tokenized KORML v0 file into a one-document stream.

    An empty or blank-only source is one empty document, an Empty.
    max_depth limits the nesting of collections as for the v1 parser.
    """
    if file.version is not korml.model.Version.v0:
        raise ValueError(f"parser v0 cannot parse version {file.version.value!r}")

    korml._limits.check_max_depth(max_depth)
    parser_v1._check_tokens(file, max_tokens)
    parser_v1._check_flow_depth(file, max_depth)
    budget = parser_v1._ParseBudget(remaining=max_work)

    document = parser_v1._parse_document(
        file.token_array,
        version=file.version,
        source_name=file.filename,
        budget=budget,
        max_depth=max_depth,
    )

    return korml.model.Stream[lexer_v0.Token](
        document_array=[document],
        filename=file.filename,
        cst=korml.model.CST(
            version=file.version,
            token_array=file.token_array,
        ),
    )
