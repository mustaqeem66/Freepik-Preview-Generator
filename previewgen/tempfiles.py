"""
PreviewGen Temp File Utilities
GUI-independent helpers for owner-marked temporary directories and diagnostic
cleanup. Cleanup failures (antivirus locks, open image handles, permission or
network filesystem errors) are always logged rather than silently swallowed.
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

OWNER_MARKER = ".previewgen_owner"
STALE_AGE_SECONDS: float = 24 * 60 * 60
MINIMUM_DELETION_AGE_SECONDS: float = 60.0  # Protect fresh directories against PID-reuse races
# Prefixes owned by PreviewGen; used to scope stale cleanup.
PREVIEWGEN_PREFIXES: tuple[str, ...] = (
    "previewgen_scan_",
    "previewgen_sync_scan_",
    "previewgen_ondemand_",
    "previewgen_batch_zip_",
    "previewgen_render_",
    "previewgen_preview_",
)


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness probe for a process id."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return True  # conservative: assume alive if we cannot tell
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def create_temp_dir(prefix: str, base_dir: Path | None = None) -> Path:
    """Create an owner-marked temporary directory owned by this process.

    ``base_dir`` lets callers co-locate a temp directory with a destination so
    that the final install can use an atomic same-filesystem ``os.replace``.
    """
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base_dir) if base_dir else None))
    try:
        import uuid
        (path / OWNER_MARKER).write_text(
            json.dumps(
                {
                    "instanceId": uuid.uuid4().hex[:12],
                    "pid": os.getpid(),
                    "created": time.time(),
                    "kind": prefix.strip("_"),
                    "user": _safe_user(),
                }
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        logging.debug("Could not write owner marker for %s: %s", path, exc)
    return path


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def safe_rmtree(path: Path | str, description: str = "temp directory") -> bool:
    """Remove a directory tree, logging (never silently swallowing) failures."""
    p = Path(path)
    try:
        if not p.exists():
            return True
        shutil.rmtree(p)
        return True
    except Exception as exc:
        logging.warning("Cleanup failure for %s %s: %s", description, p, exc)
        return False


def cleanup_stale_temp_dirs(
    base: Path | None = None,
    max_age_seconds: float = STALE_AGE_SECONDS,
) -> int:
    """
    Remove leftover PreviewGen temporary directories whose owning process is
    dead, or that are older than ``max_age_seconds``. Returns the count removed.

    Directories lacking an owner marker are only removed once they exceed the
    stale age threshold, so an in-flight legacy directory is never clobbered.
    """
    base = base or Path(tempfile.gettempdir())
    try:
        candidates: Iterable[Path] = list(base.iterdir())
    except Exception:
        return 0

    now = time.time()
    removed = 0
    for entry in candidates:
        try:
            if not entry.is_dir():
                continue
            if not any(entry.name.startswith(pfx) for pfx in PREVIEWGEN_PREFIXES):
                continue

            owner_pid: int | None = None
            created: float | None = None
            marker = entry / OWNER_MARKER
            if marker.is_file():
                try:
                    data = json.loads(marker.read_text(encoding="utf-8"))
                    if data.get("pid") is not None:
                        owner_pid = int(data["pid"])
                    if data.get("created") is not None:
                        created = float(data["created"])
                except Exception:
                    owner_pid = None

            reference = created if created is not None else entry.stat().st_mtime
            age = now - reference
            # Protected against immediate startup races:
            # do not delete fresh directories under MINIMUM_DELETION_AGE_SECONDS
            is_stale = age > max_age_seconds
            owner_dead = owner_pid is not None and not _pid_alive(owner_pid)
            eligible = (owner_dead and age >= MINIMUM_DELETION_AGE_SECONDS) or (owner_pid is None and is_stale)

            if eligible and safe_rmtree(entry, "stale temp"):
                removed += 1
        except Exception as exc:
            logging.debug("Stale temp inspection skipped for %s: %s", entry, exc)

    if removed:
        logging.info("Startup cleanup removed %d stale PreviewGen temp directories", removed)
    return removed
