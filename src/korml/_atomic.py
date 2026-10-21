# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Atomically replace a file without following a final-component output symlink."""

import os
import pathlib
import stat
import tempfile


def write_bytes(path: str | pathlib.Path, data: bytes) -> None:
    """Write complete bytes before replacing *path*.

    The temporary file is created in the destination directory so replacement
    is atomic on a single filesystem. An existing final-component symlink is
    replaced, never opened. The directory must be trusted against concurrent
    renames or symlink swaps by other users.
    """
    destination = pathlib.Path(path)
    parent = destination.parent
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            try:
                previous = destination.lstat()
            except FileNotFoundError:
                previous = None
            if previous is not None and stat.S_ISREG(previous.st_mode) and hasattr(os, "fchmod"):
                # Preserve existing file permissions, including private configs.
                os.fchmod(stream.fileno(), stat.S_IMODE(previous.st_mode))
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        if os.name == "posix":
            # Persist the directory rename, not just the temporary file data.
            directory_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
