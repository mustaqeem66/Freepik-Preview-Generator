"""
PreviewGen Error Taxonomy
Stable, machine-readable error codes plus a classifier that maps exceptions to
a code and a clean user-facing message. Full exception details must only be
written to local logs, never surfaced verbatim through the JS bridge.
"""
from __future__ import annotations

import errno


class ErrorCode:
    """Stable error codes returned across the JavaScript bridge."""

    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    UNAUTHORIZED_PATH = "UNAUTHORIZED_PATH"
    FOLDER_NOT_FOUND = "FOLDER_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DISK_FULL = "DISK_FULL"
    RENDERER_MISSING = "RENDERER_MISSING"
    RENDER_TIMEOUT = "RENDER_TIMEOUT"
    CORRUPT_ASSET = "CORRUPT_ASSET"
    SCAN_CANCELLED = "SCAN_CANCELLED"
    SCAN_TRUNCATED = "SCAN_TRUNCATED"
    OUTPUT_LOCKED = "OUTPUT_LOCKED"
    OUTPUT_FOLDER_REQUIRED = "OUTPUT_FOLDER_REQUIRED"
    REPORT_WRITE_FAILED = "REPORT_WRITE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_MESSAGES: dict[str, str] = {
    ErrorCode.INVALID_CONFIGURATION: "The provided settings are invalid.",
    ErrorCode.UNAUTHORIZED_PATH: "Access to this location is not permitted.",
    ErrorCode.FOLDER_NOT_FOUND: "The selected folder no longer exists.",
    ErrorCode.PERMISSION_DENIED: "Permission was denied for this location.",
    ErrorCode.DISK_FULL: "There is not enough disk space to complete the task.",
    ErrorCode.RENDERER_MISSING: "A required renderer component is not available.",
    ErrorCode.RENDER_TIMEOUT: "Rendering this file took too long and was stopped.",
    ErrorCode.CORRUPT_ASSET: "This file could not be read or is not a supported asset.",
    ErrorCode.SCAN_CANCELLED: "The scan was cancelled.",
    ErrorCode.SCAN_TRUNCATED: "The scan stopped before it finished.",
    ErrorCode.OUTPUT_LOCKED: "The output folder is in use by another PreviewGen process.",
    ErrorCode.OUTPUT_FOLDER_REQUIRED: "Choose an output folder before exporting.",
    ErrorCode.REPORT_WRITE_FAILED: "The batch report could not be saved.",
    ErrorCode.INTERNAL_ERROR: "An unexpected error occurred.",
}


def user_message(code: str) -> str:
    """Return the clean, user-facing message for a stable error code."""
    return _MESSAGES.get(code, _MESSAGES[ErrorCode.INTERNAL_ERROR])


def classify_exception(exc: BaseException) -> tuple[str, str]:
    """
    Map an exception to a ``(code, user_message)`` pair.

    The returned message is always clean and free of stack details; callers are
    expected to log the original exception locally.
    """
    if isinstance(exc, PermissionError):
        return ErrorCode.PERMISSION_DENIED, user_message(ErrorCode.PERMISSION_DENIED)

    if isinstance(exc, FileNotFoundError):
        return ErrorCode.FOLDER_NOT_FOUND, user_message(ErrorCode.FOLDER_NOT_FOUND)

    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return ErrorCode.RENDERER_MISSING, user_message(ErrorCode.RENDERER_MISSING)

    if isinstance(exc, TimeoutError):
        return ErrorCode.RENDER_TIMEOUT, user_message(ErrorCode.RENDER_TIMEOUT)

    if isinstance(exc, OSError):
        if exc.errno in (errno.EACCES, errno.EPERM):
            return ErrorCode.PERMISSION_DENIED, user_message(ErrorCode.PERMISSION_DENIED)
        if exc.errno == errno.ENOSPC:
            return ErrorCode.DISK_FULL, user_message(ErrorCode.DISK_FULL)
        if exc.errno == errno.ENOENT:
            return ErrorCode.FOLDER_NOT_FOUND, user_message(ErrorCode.FOLDER_NOT_FOUND)

    text = str(exc).lower()

    if "locked by another" in text or "currently locked" in text:
        return ErrorCode.OUTPUT_LOCKED, user_message(ErrorCode.OUTPUT_LOCKED)
    if "cancel" in text:
        return ErrorCode.SCAN_CANCELLED, user_message(ErrorCode.SCAN_CANCELLED)
    if "timed out" in text or "timeout" in text:
        return ErrorCode.RENDER_TIMEOUT, user_message(ErrorCode.RENDER_TIMEOUT)
    if "pip install" in text or "is required" in text or "not available" in text:
        return ErrorCode.RENDERER_MISSING, user_message(ErrorCode.RENDERER_MISSING)
    if isinstance(exc, ValueError) and any(
        kw in text for kw in ("configuration", "out of bounds", "unknown", "must be a dictionary")
    ):
        return ErrorCode.INVALID_CONFIGURATION, user_message(ErrorCode.INVALID_CONFIGURATION)

    if isinstance(exc, (ValueError, RuntimeError)) or any(
        kw in text
        for kw in (
            "could not", "invalid", "not a supported", "unsupported", "no embedded",
            "does not contain", "exceeds", "empty", "corrupt", "no supported",
            "unrecognized", "truncated", "cannot identify", "unidentified",
            "identifiedimageerror", "decompressionbomb",
        )
    ):
        return ErrorCode.CORRUPT_ASSET, user_message(ErrorCode.CORRUPT_ASSET)

    return ErrorCode.INTERNAL_ERROR, user_message(ErrorCode.INTERNAL_ERROR)
