"""
PreviewGen Desktop Runtime
GUI entry point. ONLY this module imports pywebview at module scope.

CLI modes and pure modules (cli, scanner, settings, api, lifecycle, renderers)
must never import this module, so they remain usable without a GUI runtime.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading

# THIS IS THE ONLY MODULE THAT IMPORTS WEBVIEW AT MODULE SCOPE
import time
import webbrowser
from pathlib import Path
from typing import Any

import webview

from previewgen.api import DesktopApi
from previewgen.dialogs import applescript_string
from previewgen.resources import get_html_dist
from previewgen.ui_watchdog import WindowHangDetector, log_thread_stacks, windows_window_responding


def show_fatal_error(title: str, message: str) -> None:
    """Show fatal error dialog appropriate for platform."""
    logging.critical("%s: %s", title, message)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
            return
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            import subprocess
            cmd = (
                f"display dialog {applescript_string(message)} with title "
                f"{applescript_string(title)} buttons {{\"OK\"}} default button \"OK\" with icon stop"
            )
            subprocess.run(["osascript", "-e", cmd], check=False, timeout=30)
            return
        except Exception:
            pass
    sys.stderr.write(f"\n[FATAL ERROR] {title}\n{message}\n\n")


def bridge_is_stalled(api: Any, now: float, quiet_seconds: float = 15.0) -> bool:
    """True when the bridge has emitted nothing for ``quiet_seconds`` during work.

    Heartbeats only advance when Python pushes an event, so a quiet bridge with
    nothing in flight is an idle app, not a frozen one.
    """
    last_hb = getattr(api, "_last_heartbeat_time", 0.0)
    if last_hb <= 0 or (now - last_hb) <= quiet_seconds:
        return False
    return bool(api.has_outstanding_work())


def start_desktop_app() -> int:
    """
    Create and run the pywebview window with the React frontend.
    This is the ONLY function that creates a webview window.

    Returns:
        Exit code (0 on success, non-zero on failure)
    """
    logging.info("Starting PreviewGen desktop runtime...")

    api = DesktopApi()
    html_dist = get_html_dist()

    if not html_dist.is_file():
        show_fatal_error(
            "PreviewGen - Missing Frontend Bundle",
            f"Cannot find frontend bundle at: {html_dist}\n\nPlease reinstall PreviewGen."
        )
        return 1

    # P0: Headless smoke test mode - validates full GUI stack without human interaction
    is_smoke = "--gui-smoke-test" in sys.argv
    if is_smoke:
        logging.info("GUI smoke test mode enabled")
        if sys.platform.startswith("linux"):
            has_gtk = bool(__import__("importlib.util").util.find_spec("gi"))
            has_qt = bool(__import__("importlib.util").util.find_spec("qtpy"))
            if not has_gtk and not has_qt:
                logging.error(
                    "Linux smoke test cannot construct a WebView: neither the gi (GTK) "
                    "nor qtpy bindings are importable. Reporting this as a pass would "
                    "certify a GUI stack that was never exercised."
                )
                return 1
    target_url = html_dist.as_uri()
    logging.info("Loading frontend from: %s", target_url)

    # Window creation with platform-resilient GUI selection and Cocoa/Win32/Linux flags
    gui_type = None
    if sys.platform == "darwin":
        gui_type = "cocoa"
    elif sys.platform == "win32":
        gui_type = "edgechromium"

    is_headless = is_smoke
    # Set PREVIEWGEN_NATIVE_TITLEBAR=1 to fall back to OS decorations on
    # systems where frameless windows are not draggable/resizable.
    custom_chrome = os.environ.get("PREVIEWGEN_NATIVE_TITLEBAR") != "1"
    window = webview.create_window(
        "PreviewGen",
        target_url,
        width=1400,
        height=900,
        min_size=(1100, 700),
        resizable=True,
        text_select=False,
        frameless=custom_chrome,
        easy_drag=False,
        on_top=False,
        background_color="#0F172A",
        js_api=api,
        hidden=is_headless,
    )
    if window is None:
        raise RuntimeError("webview.create_window returned no window; a GUI backend is unavailable")
    # Bind api to window
    api._set_window(window, custom_chrome=custom_chrome)

    # Navigation lockdown - block external navigation
    def on_navigating(url: str) -> bool:
        if not url:
            return False
        target_base = target_url.split("#")[0].split("?")[0].rstrip("/") if target_url else ""
        clean_url = url.split("#")[0].split("?")[0].rstrip("/")
        is_dev = False  # Could check for PREVIEWGEN_DEV=1
        is_local_packaged = bool(target_base and clean_url == target_base)

        if is_dev or is_local_packaged:
            return True

        logging.warning("Blocked privileged window navigation to external origin: %s", url)
        from urllib.parse import urlparse
        if urlparse(url).scheme in ("http", "https"):
            try:
                webbrowser.open(url)
            except Exception as e:
                logging.debug("Could not open external URL: %s", e)
        return False

    with contextlib.suppress(Exception):
        window.events.navigating += on_navigating

    # Independent Windows message-pump health checks also work when no assets
    # have been selected (the old bridge heartbeat cannot detect idle GUI hangs).
    # Diagnostics are passive: never force-quit, restart or dismiss a native dialog.
    watchdog_stop = threading.Event()

    def _watchdog_loop() -> None:
        detector = WindowHangDetector(threshold=3, cooldown_seconds=60)
        last_bridge_report = 0.0
        while not watchdog_stop.wait(3.0):
            try:
                now = time.time()
                if detector.observe(windows_window_responding(), now):
                    log_thread_stacks(
                        "Windows UI message pump did not answer three consecutive "
                        "bounded WM_NULL probes. A native modal dialog or heavy load "
                        "can also trigger this diagnostic."
                    )
                if bridge_is_stalled(api, now) and now - last_bridge_report >= 60.0:
                    last_bridge_report = now
                    log_thread_stacks(
                        "Backend operation active but no outgoing bridge events for >15s"
                    )
            except Exception:
                logging.debug("UI watchdog probe failed", exc_info=True)

    threading.Thread(
        target=_watchdog_loop, name="previewgen-ui-watchdog", daemon=True,
    ).start()

    try:
        start_kwargs: dict[str, Any] = {"debug": False}
        if gui_type:
            start_kwargs["gui"] = gui_type
        if is_smoke and gui_type:
            def _auto_close_smoke(smoke_window: Any = window) -> None:
                marker = os.environ.get("PREVIEWGEN_READY_MARKER")
                for _ in range(30):
                    if marker and Path(marker).is_file():
                        break
                    time.sleep(0.5)
                with contextlib.suppress(Exception):
                    smoke_window.destroy()
                # Terminate smoke test process so host subshell is never left waiting on Cocoa/Win32 event loops
                threading.Timer(1.0, lambda: os._exit(0)).start()
            threading.Thread(target=_auto_close_smoke, daemon=True).start()
        # P1 root cause 8: Do not attempt to re-start pywebview in the same process
        # after a failure. A partial initialization leaves native state that causes hangs.
        webview.start(**start_kwargs)
    except Exception as exc:
        show_fatal_error("PreviewGen - GUI Failure", f"Failed to initialize webview window: {exc}")
        raise
    finally:
        watchdog_stop.set()
        api.cleanup()
    return 0

def main() -> int:
    """
    Backward-compatible launcher.

    Prefer ``previewgen.entrypoint.main``; this delegates there so that CLI
    modes remain GUI-independent even when invoked via this module.
    """
    from previewgen.entrypoint import main as _entry
    return _entry()


if __name__ == "__main__":
    sys.exit(main())
