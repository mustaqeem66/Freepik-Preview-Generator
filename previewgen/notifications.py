"""Best-effort native desktop notifications for opt-in batch completion.

Failures are deliberately non-fatal. Notification commands never execute user
content as shell code, do not keep the bridge waiting, and have bounded timeouts.
Windows delivery requires OS notification permissions and a registered app ID.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

APP_NAME = "PreviewGen"
WINDOWS_APP_ID = "PreviewGen.Studio"


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)) if sys.platform == "win32" else 0


def _run_hidden(command: list[str], timeout: float = 6.0) -> bool:
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=timeout,
            creationflags=_creation_flags(), check=False,
        )
        if result.returncode != 0:
            logging.debug("Notification command exited %d", result.returncode)
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.debug("Desktop notifications unavailable: %s", exc)
        return False


def ps_quote(text: str) -> str:
    """Encode data as a PowerShell single-quoted literal, not executable code."""
    return "'" + text.replace("'", "''").replace("\r", " ").replace("\n", " ") + "'"


def applescript_quote(text: str) -> str:
    """Encode data as an AppleScript string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ") + '"'


def _toast_windows(title: str, message: str) -> bool:
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$t = $x.GetElementsByTagName('text'); "
        "$t.Item(0).AppendChild($x.CreateTextNode(" + ps_quote(title) + ")) | Out-Null; "
        "$t.Item(1).AppendChild($x.CreateTextNode(" + ps_quote(message) + ")) | Out-Null; "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        + ps_quote(WINDOWS_APP_ID) + ").Show($toast)"
    )
    return _run_hidden(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])


def notify(title: str, message: str) -> bool:
    """Return command dispatch status, not a guarantee of OS presentation."""
    title = (title or APP_NAME).strip()[:120]
    message = (message or "").strip()[:250]
    try:
        if sys.platform == "win32":
            return _toast_windows(title, message)
        if sys.platform == "darwin":
            script = "display notification " + applescript_quote(message) + " with title " + applescript_quote(title)
            return _run_hidden(["osascript", "-e", script])
        if sys.platform.startswith("linux"):
            return _run_hidden(["notify-send", "--app-name", APP_NAME, title, message])
    except Exception:
        logging.exception("Unexpected notification dispatch failure")
    return False


def batch_summary_text(summary: dict[str, Any]) -> str:
    success = max(0, int(summary.get("success", 0) or 0))
    failed = max(0, int(summary.get("failed", 0) or 0))
    skipped = max(0, int(summary.get("skipped", 0) or 0))
    status = str(summary.get("status", ""))
    if summary.get("cancelled") or status == "cancelled":
        title = "Batch cancelled"
    elif status == "failed":
        title = "Batch failed"
    elif failed or status == "completed_with_errors":
        title = "Batch completed with errors"
    elif summary.get("truncated") or status == "completed_with_warnings":
        title = "Batch completed with warnings"
    else:
        title = "Batch complete"
    parts = [f"{success} saved"]
    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    return title + ": " + " · ".join(parts)


def notify_batch_finished(summary: dict[str, Any]) -> bool:
    return notify(APP_NAME, batch_summary_text(summary))
