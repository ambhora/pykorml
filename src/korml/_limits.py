# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Default resource limits for processing untrusted documents."""

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_TOKENS = 100_000
MAX_PARSE_WORK = 1_000_000

# The default deepest nesting of collections that korml reads or writes: a
# collection inside 127 others is accepted, one inside 128 is not. The parser,
# the emitter, the model and the schema code recurse once per level, and the
# limit keeps them well inside Python's recursion limit. Every entry point
# that walks a document takes it as max_depth; the rules require at least 64.
MAX_NESTING_DEPTH = 128


def check_max_depth(max_depth: int | None) -> None:
    """
    Raise if max_depth is not a valid nesting limit.

    A limit is a positive integer, or None for no limit imposed by korml.
    With None, Python's own recursion limit still ends very deep nesting;
    the entry points turn the RecursionError into a korml error with the
    code TOO_DEEP.

    @param max_depth The limit to check.
    """
    if max_depth is None:
        return

    if isinstance(max_depth, bool) or not isinstance(max_depth, int):
        raise TypeError(f"max_depth must be an integer or None, not {type(max_depth).__name__}")

    if max_depth <= 0:
        raise ValueError(f"max_depth must be positive, not {max_depth}")


def is_too_deep(depth: int, max_depth: int | None) -> bool:
    """
    Return whether a collection inside depth others breaks the nesting limit.

    depth counts the collections that enclose this one, so the root
    collection has depth 0 and is level 1; max_depth is the deepest level
    allowed.

    @param depth The number of collections that enclose this one.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return True if the collection breaks the limit.
    """
    return max_depth is not None and depth >= max_depth


def too_deep_message(max_depth: int | None) -> str:
    """
    Return the message of a TOO_DEEP error.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @return The message, which names the limit.
    """
    if max_depth is None:
        return "collections are nested deeper than Python's recursion limit allows"

    return f"collections are nested deeper than {max_depth} levels"


def check_input_size(text: str, *, max_input_bytes: int | None, filename: str) -> None:
    """
    Raise a CompilerError if text is larger than max_input_bytes.

    @param text The source text.

    @param max_input_bytes The largest source accepted, in bytes, or None for no limit.

    @param filename The name of the source, for diagnostics.
    """
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

    @param count The number of tokens the lexer holds.

    @param max_tokens The largest number of tokens accepted, or None for no limit.

    @param filename The name of the source, for diagnostics.
    """
    import korml.error

    if max_tokens is not None and count >= max_tokens:
        raise korml.error.CompilerError(
            message=f"token count exceeds {max_tokens}",
            source_name=filename,
            code="TOO_MANY_TOKENS",
        )
