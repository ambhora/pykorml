# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# --------------------------------------------------------------------------------------------------

"""KORML v0 emitter."""

import enum

import korml.emitter.v1
import korml.model

__all__ = ["ErrorCode", "emit"]


class ErrorCode(str, enum.Enum):
    UNSUPPORTED_VALUE = "UNSUPPORTED_VALUE"
    MULTIPLE_DOCUMENTS = "MULTIPLE_DOCUMENTS"

    def __str__(self) -> str:
        return self.value


def emit(stream: korml.model.Stream[object]) -> str:
    """Emit a KORML v0 source string from a stream with at most one document."""
    if stream.version is not korml.model.Version.v0:
        raise ValueError(f"emitter v0 cannot emit version {stream.version.value!r}")

    if len(stream.document_array) > 1:
        raise ValueError("emitter v0 cannot emit multiple documents")

    if not stream.document_array:
        return ""

    return "\n".join(korml.emitter.v1._emit_value(stream.document_array[0], indent=0)) + "\n"
