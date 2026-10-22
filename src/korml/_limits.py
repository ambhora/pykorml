# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Default resource limits for processing untrusted documents."""

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_TOKENS = 100_000
MAX_PARSE_WORK = 1_000_000


def check_input_size(text: str, *, max_input_bytes: int | None, filename: str) -> None:
    import korml.error

    if max_input_bytes is not None and (
        len(text) > max_input_bytes
        or len(text.encode("utf-8", errors="surrogatepass")) > max_input_bytes
    ):
        raise korml.error.CompilerError(
            message=f"input exceeds {max_input_bytes} bytes",
            source_name=filename,
            code="INPUT_TOO_LARGE",
        )


def check_token_count(count: int, *, max_tokens: int | None, filename: str) -> None:
    """Raise if a lexer that already holds count tokens may not add another.

    The lexers call this before each token, so an input with too many tokens
    is rejected after max_tokens tokens rather than after building them all.
    """
    import korml.error

    if max_tokens is not None and count >= max_tokens:
        raise korml.error.CompilerError(
            message=f"token count exceeds {max_tokens}",
            source_name=filename,
            code="TOO_MANY_TOKENS",
        )
