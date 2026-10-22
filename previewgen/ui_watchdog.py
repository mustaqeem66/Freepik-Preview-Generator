"""Diagnostic-only probe for frozen Windows desktop windows.

The prior watchdog inspected *backend* work, but an idle pywebview GUI can
stop processing Windows messages without a backend operation. This module
checks that independent signal. It never force-closes or restarts the app.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import traceback
from ctypes import wintypes

DEFAULT_HANG_THRESHOLD = 3
DEFAULT_REPORT_COOLDOWN_SECONDS = 60.0


def windows_window_responding(title: str = "PreviewGen", timeout_ms: int = 750) -> bool | None:
    """Return True/False for this process's top-level window, None if unavailable.

    SendMessageTimeout(WM_NULL) tests message-pump responsiveness on another
    thread, with SMTO_ABORTIFHUNG and an explicit timeout. The probe is only
    diagnostic: a modal OS dialog or machine under load may also cause timeouts.
    """
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32  # pyrefly: ignore[missing-attribute]  # Windows-only, guarded above
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
        ]
        user32.SendMessageTimeoutW.restype = wintypes.LPARAM

        handle = user32.FindWindowW(None, title)
        if not handle:
            return None
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value != os.getpid():
            return None

        result = ctypes.c_size_t()
        # WM_NULL=0, SMTO_ABORTIFHUNG=0x2; bound each check to <1 second.
        return bool(user32.SendMessageTimeoutW(
            handle, 0, 0, 0, 0x0002, timeout_ms, ctypes.byref(result)
        ))
    except (AttributeError, OSError, TypeError, ValueError):
        logging.debug("Windows message-pump diagnostic unavailable", exc_info=True)
        return None


class WindowHangDetector:
    """Require several consecutive failed probes and rate-limit stack dumps."""

    def __init__(
        self, threshold: int = DEFAULT_HANG_THRESHOLD,
        cooldown_seconds: float = DEFAULT_REPORT_COOLDOWN_SECONDS,
    ) -> None:
        self.threshold = max(1, threshold)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self.failures = 0
        self.last_report_at: float | None = None

    def observe(self, responding: bool | None, now: float) -> bool:
        if responding is not False:
            self.failures = 0
            return False
        self.failures += 1
        if self.failures < self.threshold:
            return False
        if self.last_report_at is not None and now - self.last_report_at < self.cooldown_seconds:
            return False
        self.last_report_at = now
        return True


def log_thread_stacks(reason: str) -> None:
    """Log every Python thread's stack for support, without freezing the GUI."""
    logging.error("HANG DIAGNOSTIC: %s", reason)
    names = {t.ident: t.name for t in threading.enumerate()}
    for ident, frame in sys._current_frames().items():
        logging.error(
            "HANG DIAGNOSTIC thread=%s name=%s:\n%s",
            ident, names.get(ident, "unknown"),
            "".join(traceback.format_stack(frame)),
        )
