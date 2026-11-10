# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""KORML v0 emitter."""

import enum

import korml._limits
import korml.emitter.v1
import korml.model

__all__ = ["ErrorCode", "emit"]


class ErrorCode(str, enum.Enum):
    """The codes of the v0 emitter."""

    UNSUPPORTED_VALUE = "UNSUPPORTED_VALUE"
    """Reserved: nothing reports this code yet."""
    MULTIPLE_DOCUMENTS = "MULTIPLE_DOCUMENTS"
    """Reserved: nothing reports this code yet. A stream of several documents is a ValueError."""

    def __str__(self) -> str:
        """
        Return the code as text.

        @return The value of the code.
        """
        return self.value


def emit(
    stream: korml.model.Stream[object],
    *,
    max_depth: int | None = korml._limits.MAX_NESTING_DEPTH,
    max_output_bytes: int | None = korml._limits.MAX_OUTPUT_BYTES,
) -> str:
    """
    Emit a KORML v0 source string from a stream with at most one document.

    An empty document, or a stream without documents, is the empty source.
    max_depth limits the nesting of collections and max_output_bytes the
    length of the source, as for the v1 emitter.

    @param stream The stream to write, of version v0.

    @param max_depth The deepest nesting of collections allowed, or None for no limit imposed by
        korml.

    @param max_output_bytes The longest source allowed, in bytes, or None for no limit.

    @return The source, empty for an empty document.
    """
    if stream.version is not korml.model.Version.v0:
        raise ValueError(f"emitter v0 cannot emit version {stream.version.value!r}")

    if len(stream.document_array) > 1:
        raise ValueError("emitter v0 cannot emit multiple documents")

    korml._limits.check_max_depth(max_depth)
    korml._limits.check_max_output_bytes(max_output_bytes)
    line_array = (
        korml.emitter.v1._emit_root(
            stream.document_array[0],
            max_depth=max_depth,
            budget=korml.emitter.v1._OutputBudget(max_output_bytes),
        )
        if stream.document_array
        else []
    )

    if not line_array:
        return ""

    return "\n".join(line_array) + "\n"
