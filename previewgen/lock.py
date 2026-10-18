"""
PreviewGen Centralized Directory Locking Service
Provides atomic, inode-safe, cross-platform directory locking with ownership metadata,
network filesystem tolerance, and deterministic cleanup.
"""
from __future__ import annotations

import contextlib
import datetime
import errno
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

LOCK_FILENAME = ".previewgen.lock"


class DirectoryLockError(RuntimeError):
    """Raised when an output directory lock is held by another process."""

    def __init__(self, message: str, code: str = "LOCKED", owner: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.owner = owner or {}


class DirectoryLock:
    """
    Centralized cross-platform directory lock.

    Guarantees:
    - Inode-race prevention: opened with 'a+b', never unlinked on release.
    - Ownership metadata: records PID, batch ID, and start timestamp into descriptor.
    - Contention vs unsupported locking: distinguishes active lock collision from
      network/virtual filesystem limitations (NFS, SMB, CIFS, WebDAV).
    - Context manager and explicit acquire/release interfaces.
    """

    def __init__(self, directory: Path | str, batch_id: str | None = None) -> None:
        self.directory = Path(directory).resolve()
        self.batch_id = batch_id
        self.lock_file = self.directory / LOCK_FILENAME
        self._handle: Any | None = None
        self._acquired = False
        self._supported = True

    @property
    def is_acquired(self) -> bool:
        return self._acquired

    @property
    def is_supported(self) -> bool:
        return self._supported

    def read_metadata(self) -> dict[str, Any] | None:
        """Inspect the current lock-file contents for owner PID and batch ID."""
        if self._handle and self._acquired:
            try:
                pos = self._handle.tell()
                self._handle.seek(0)
                raw = self._handle.read()
                self._handle.seek(pos)
                content = raw.decode("utf-8", "replace").strip()
                if content.startswith("{"):
                    return json.loads(content)
                data: dict[str, Any] = {}
                for line in content.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        data[k.strip()] = v.strip()
                if data:
                    return data
            except Exception:
                pass
        if not self.lock_file.is_file():
            return None
        try:
            content = self.lock_file.read_text(encoding="utf-8").strip()
            if not content:
                return None
            # Support both key=value format and JSON metadata
            if content.startswith("{"):
                return json.loads(content)
            data = {}
            for line in content.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
            return data
        except Exception:
            return None

    def acquire(self) -> bool:
        """
        Acquire non-blocking exclusive lock on the directory.
        Raises DirectoryLockError if held by another live process.
        """
        if self._acquired:
            return True

        self.directory.mkdir(parents=True, exist_ok=True)
        handle = None
        try:
            handle = open(self.lock_file, "a+b")  # noqa: SIM115
            fd = handle.fileno()

            if sys.platform != "win32":
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                handle.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            # Acquired lock: write ownership metadata into descriptor
            try:
                handle.seek(0)
                handle.truncate(0)
                started_at = datetime.datetime.now(datetime.UTC).isoformat()
                meta = {
                    "pid": os.getpid(),
                    "batchId": self.batch_id,
                    "startedAt": started_at,
                }
                handle.write(json.dumps(meta).encode("utf-8") + b"\n")
                handle.flush()
            except Exception as write_err:
                logging.debug("Could not write lock metadata: %s", write_err)

            self._handle = handle
            self._acquired = True
            return True

        except BlockingIOError as exc:
            if handle:
                with contextlib.suppress(Exception):
                    handle.close()
            owner = self.read_metadata()
            raise DirectoryLockError(
                f"Output directory is currently locked by another PreviewGen process: {self.directory}",
                code="LOCKED",
                owner=owner,
            ) from exc

        except OSError as exc:
            is_contention = exc.errno in (
                getattr(errno, "EAGAIN", 11),
                getattr(errno, "EWOULDBLOCK", 11),
                getattr(errno, "EACCES", 13),
                getattr(errno, "EDEADLK", 35),
            )
            is_unsupported = exc.errno in (
                getattr(errno, "ENOSYS", 38),
                getattr(errno, "EOPNOTSUPP", 95),
                getattr(errno, "ENOTSUP", 95),
            )

            if is_contention and not is_unsupported:
                if handle:
                    with contextlib.suppress(Exception):
                        handle.close()
                owner = self.read_metadata()
                raise DirectoryLockError(
                    f"Output directory is currently locked by another PreviewGen process: {self.directory}",
                    code="LOCKED",
                    owner=owner,
                ) from exc
            elif is_unsupported:
                logging.warning(
                    "Locking is not supported on output filesystem '%s' (errno=%s). Proceeding without directory lock.",
                    self.directory,
                    exc.errno,
                )
                self._supported = False
                if handle:
                    with contextlib.suppress(Exception):
                        handle.close()
                self._acquired = True
                return True
            else:
                if handle:
                    handle.close()
                raise

    def release(self) -> None:
        """
        Release the lock descriptor and close the handle.
        DOES NOT unlink lock_file to preserve inode stability.
        """
        if self._handle and self._supported:
            try:
                fd = self._handle.fileno()
                if sys.platform != "win32":
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
                else:
                    import msvcrt
                    self._handle.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except Exception as exc:
                logging.debug("DirectoryLock unlock notice: %s", exc)
            finally:
                with contextlib.suppress(Exception):
                    self._handle.close()
                self._handle = None

        self._acquired = False

    def __enter__(self) -> DirectoryLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
