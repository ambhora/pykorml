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
