"""
PreviewGen Settings Module
GUI-independent settings persistence with schema versioning and atomic writes.
"""
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict


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


def load_settings() -> Dict[str, Any]:
    """
    Load and validate user preferences from disk.
    Returns validated settings with schemaVersion 2.
    """
    def _load_and_validate(f_path: Path) -> Dict[str, Any] | None:
        try:
            raw = json.loads(f_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            # Schema version migration / verification
            version = raw.get("schemaVersion") or raw.get("_schema_version", 1)
            clean = {k: v for k, v in raw.items() if isinstance(k, str) and not k.startswith("_")}
            clean["schemaVersion"] = 2
            return clean
        except Exception as exc:
            # Silently fail - caller handles None
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
            except Exception:
                pass

    # Attempt fallback to backup
    if SETTINGS_BACKUP.is_file():
        backup_val = _load_and_validate(SETTINGS_BACKUP)
        if backup_val is not None:
            return backup_val

    # Return defaults with schema version
    return {"schemaVersion": 2}


def save_settings(settings_dict: Dict[str, Any]) -> bool:
    """
    Save user preferences atomically to disk with backup and schema version.
    Returns True on success, False on failure.
    """
    if not isinstance(settings_dict, dict):
        return False
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 2,
            **{k: v for k, v in settings_dict.items() if isinstance(k, str) and not k.startswith("_") and k != "schemaVersion"}
        }
        serialized = json.dumps(payload, indent=2)
        temp_file = SETTINGS_DIR / f"settings_{os.getpid()}_{threading.get_ident()}.tmp"
        temp_file.write_text(serialized, encoding="utf-8")
        # Sync to physical storage
        with open(temp_file, "a+", encoding="utf-8") as f:
            f.flush()
            os.fsync(f.fileno())
        if SETTINGS_FILE.is_file():
            try:
                shutil.copy2(SETTINGS_FILE, SETTINGS_BACKUP)
            except Exception:
                pass
        temp_file.replace(SETTINGS_FILE)
        return True
    except Exception as exc:
        # Error is logged by caller
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
    handler = __import__('logging.handlers').handlers.RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handlers: list = [handler]
    # For frozen GUI apps on Windows without console, sys.stdout can be None or raise OSError 22 on write
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        if sys.stdout is not None:
            try:
                handlers.append(__import__('logging').StreamHandler(sys.stdout))
            except Exception:
                pass
    __import__('logging').basicConfig(
        level=__import__('logging').INFO,
        handlers=handlers,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    import platform
    __import__('logging').info(
        "Starting PreviewGen platform=%s python=%s frozen=%s",
        platform.platform(),
        sys.version,
        getattr(sys, "frozen", False),
    )
    return log_file