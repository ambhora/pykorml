# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""KORML v0 token model.

v0 uses the same document-body token kinds as v1, but it has no stream framing:
there is no version directive and there are no document start/end markers in a
valid v0 source.
"""

from korml.lexer.v1 import ErrorCode, File, Token, TokenType, make_token, make_token_array

__all__ = [
    "TokenType",
    "Token",
    "File",
    "ErrorCode",
    "make_token",
    "make_token_array",
]
