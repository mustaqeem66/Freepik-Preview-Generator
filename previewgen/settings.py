"""
PreviewGen Settings Module
GUI-independent settings persistence with schema versioning and atomic writes.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from previewgen.settings_schema import sanitize_settings, validate_settings


def get_settings_directory() -> Path:
    """Get platform-appropriate settings directory."""
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "PreviewGen"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PreviewGen"
    return Path.home() / ".config" / "previewgen"


SETTINGS_DIR = get_settings_directory()
SETTINGS_FILE = SETTINGS_DIR / "settings.v1.json"
SETTINGS_BACKUP = SETTINGS_DIR / "settings.v1.json.bak"
_settings_lock = threading.Lock()
_current_revision = 0


def get_current_revision() -> int:
    with _settings_lock:
        return _current_revision


def set_current_revision(rev: int) -> None:
    global _current_revision
    with _settings_lock:
        _current_revision = max(_current_revision, rev)
def load_settings() -> dict[str, Any]:
    """Load and validate user preferences from disk."""
    def _load_and_validate(f_path: Path) -> dict[str, Any] | None:
        try:
            raw = json.loads(f_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            # Schema version migration / verification, then validate against the
            # canonical schema so only well-formed values are ever returned.
            clean = sanitize_settings(raw)
            clean["schemaVersion"] = 2
            if "revision" in raw and isinstance(raw["revision"], int):
                set_current_revision(raw["revision"])
                clean["revision"] = raw["revision"]
            return clean
        except Exception:
            return None

    # Try primary settings file
    if SETTINGS_FILE.is_file():
        validated = _load_and_validate(SETTINGS_FILE)
        if validated is not None:
            return validated
        else:
            # Quarantine corrupted primary settings file
            try:
                quarantine_name = f"settings.corrupt.{int(__import__('time').time())}.json"
                shutil.move(SETTINGS_FILE, SETTINGS_DIR / quarantine_name)
                logging.warning("Corrupt settings quarantined to %s", quarantine_name)
            except Exception as exc:
                logging.warning("Could not quarantine corrupt settings file %s: %s", SETTINGS_FILE, exc)

    # Attempt fallback to backup
    if SETTINGS_BACKUP.is_file():
        backup_val = _load_and_validate(SETTINGS_BACKUP)
        if backup_val is not None:
            return backup_val

    # Return defaults with schema version
    return {"schemaVersion": 2}

def save_settings(settings_dict: dict[str, Any], max_retries: int = 3) -> bool:
    """
    Save user preferences atomically to disk with backup, schema version, and retry logic.
    Enforces monotonic revision ordering: rejects writes older than current revision.
    Returns True on success, False on failure.
    """
    global _current_revision
    if not isinstance(settings_dict, dict):
        return False

    # Enforce monotonic revision check (Finding 4)
    incoming_rev = settings_dict.get("revision")
    if incoming_rev is not None:
        try:
            incoming_rev = int(incoming_rev)
        except (ValueError, TypeError):
            incoming_rev = None

    if incoming_rev is not None:
        with _settings_lock:
            # 1. Read persisted revision from disk to guarantee durability across restarts and bridge instances
            stored_rev = _current_revision
            if SETTINGS_FILE.is_file():
                try:
                    disk_content = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                    if isinstance(disk_content, dict) and "revision" in disk_content:
                        stored_rev = max(stored_rev, int(disk_content["revision"]))
                except Exception:
                    pass

            if incoming_rev < stored_rev:
                logging.warning(
                    "Stale settings write rejected: incoming revision %d < stored revision %d",
                    incoming_rev,
                    stored_rev,
                )
                return False
    # Validate against the canonical schema. Unknown keys and out-of-range
    # values are dropped (and logged) so corrupt settings never reach disk.
    # ``revision`` is trusted metadata (already monotonic-checked above) and is
    # attached only *after* validation so it is never mistaken for user input.
    payload = sanitize_settings(settings_dict)
    payload["schemaVersion"] = 2
    remaining_errors = validate_settings(payload)
    if remaining_errors:
        logging.warning("Refusing to persist invalid settings: %s", "; ".join(remaining_errors))
        return False
    if incoming_rev is not None:
        payload["revision"] = incoming_rev
    # Retry configuration: immediate, 250ms, 1s (bounded by max_retries)
    retry_delays = [0.0, 0.25, 1.0][: max(1, min(max_retries, 3))]

    for attempt, delay in enumerate(retry_delays):
        if attempt > 0:
            time.sleep(delay)

        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(payload, indent=2)
            temp_file = SETTINGS_DIR / f"settings_{os.getpid()}_{threading.get_ident()}_{attempt}.tmp"
            temp_file.write_text(serialized, encoding="utf-8")
            # Sync to physical storage
            with open(temp_file, "a+", encoding="utf-8") as f:
                f.flush()
                os.fsync(f.fileno())
            # Re-check while committing: an older writer may have prepared its
            # temp file before a newer revision finished its own write.
            with _settings_lock:
                if incoming_rev is not None and incoming_rev < _current_revision:
                    temp_file.unlink(missing_ok=True)
                    return False
                if SETTINGS_FILE.is_file():
                    try:
                        shutil.copy2(SETTINGS_FILE, SETTINGS_BACKUP)
                    except Exception as exc:
                        logging.debug("Settings backup copy notice: %s", exc)
                temp_file.replace(SETTINGS_FILE)
                if incoming_rev is not None:
                    _current_revision = max(_current_revision, incoming_rev)
            return True
        except Exception as exc:
            if attempt == len(retry_delays) - 1:
                logging.warning("Atomic settings write failed after %d retries: %s", len(retry_delays), exc)
            continue

    return False


def get_log_directory() -> Path:
    """Get platform-appropriate log directory."""
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "PreviewGen" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "PreviewGen"
    return Path.home() / ".local" / "state" / "previewgen"

def configure_logging() -> Path:
    """Configure application logging."""
    log_dir = get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "previewgen.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handlers: list = [handler]
    # For frozen GUI apps on Windows without console, sys.stdout can be None or raise OSError 22 on write
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        if sys.stdout is not None:
            with contextlib.suppress(Exception):
                handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    import platform
    logging.info(
        "Starting PreviewGen platform=%s python=%s frozen=%s",
        platform.platform(),
        sys.version,
        getattr(sys, "frozen", False),
    )
    return log_file
