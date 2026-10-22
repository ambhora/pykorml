# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# ------------------------------------------------------------------------------

"""Atomic output replacement, without following final-component symlinks."""

import os
import pathlib
import secrets
import stat
import tempfile

import korml.error


def write_bytes(
    path: str | pathlib.Path,
    data: bytes,
    *,
    dangerous_allow_writing_to_symlink: bool,
) -> None:
    """Write a complete new file and atomically replace *path*.

    A symbolic link at *path* is refused with UnsafeOutputError: a link
    planted there would redirect the output to any file the user can write.
    With dangerous_allow_writing_to_symlink, the file the link points to is
    replaced instead, and the link is kept. Symlinked parent directories are
    followed either way; whoever controls a parent directory controls the
    path anyway.

    On POSIX, directory-relative operations pin the parent directory during
    the write and rename, so a link appearing at the final component after
    the check is refused too. On other platforms, atomic replace is used
    without directory-relative operations.
    """
    destination = pathlib.Path(path)

    if destination.is_symlink():
        if not dangerous_allow_writing_to_symlink:
            raise korml.error.UnsafeOutputError(
                message="refusing to write through a symbolic link",
                path=str(destination),
            )
        destination = pathlib.Path(os.path.realpath(destination))

    if os.name == "posix":
        _write_posix(destination, data)
    else:
        _write_portable(destination, data)


def _write_posix(destination: pathlib.Path, data: bytes) -> None:
    parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    temporary_name = f".{destination.name}.{secrets.token_hex(12)}.tmp"
    try:
        fd = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                try:
                    previous = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    previous = None
                # A link that appeared after the check in write_bytes.
                if previous is not None and stat.S_ISLNK(previous.st_mode):
                    raise korml.error.UnsafeOutputError(
                        message="output became a symbolic link while writing",
                        path=str(destination),
                    )
                if previous is not None and stat.S_ISREG(previous.st_mode):
                    os.fchmod(stream.fileno(), stat.S_IMODE(previous.st_mode))
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary_name,
                destination.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
    finally:
        os.close(parent_fd)


def _write_portable(destination: pathlib.Path, data: bytes) -> None:
    # Non-POSIX fallback: secure temporary creation and atomic replacement.
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            try:
                previous = destination.lstat()
            except FileNotFoundError:
                previous = None
            if previous is not None and stat.S_ISREG(previous.st_mode) and hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), stat.S_IMODE(previous.st_mode))
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
