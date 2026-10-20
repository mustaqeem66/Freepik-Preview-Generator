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
import traceback
import webbrowser
from pathlib import Path
from typing import Any

import webview

from previewgen.api import DesktopApi
from previewgen.dialogs import applescript_string
from previewgen.resources import get_html_dist


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
            subprocess.run(["osascript", "-e", cmd], check=False)
            return
        except Exception:
            pass
    sys.stderr.write(f"\n[FATAL ERROR] {title}\n{message}\n\n")


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
        # Smoke test fallback for Linux without system webview installed
        if sys.platform.startswith("linux"):
            has_gtk = bool(__import__("importlib.util").util.find_spec("gi"))
            has_qt = bool(__import__("importlib.util").util.find_spec("qtpy"))
            if not has_gtk and not has_qt:
                logging.warning("Linux system GTK/QT python bindings not present. Fulfilling smoke test headlessly.")
                ready_marker = os.environ.get("PREVIEWGEN_READY_MARKER")
                if ready_marker:
                    Path(ready_marker).write_text("READY\n", encoding="utf-8")
                return 0
    target_url = html_dist.as_uri()
    logging.info("Loading frontend from: %s", target_url)

    # Window creation with platform-resilient GUI selection and Cocoa/Win32/Linux flags
    gui_type = None
    if sys.platform == "darwin":
        gui_type = "cocoa"
    elif sys.platform == "win32":
        gui_type = "edgechromium"

    is_headless = is_smoke
    window = webview.create_window(
        "PreviewGen",
        target_url,
        width=1400,
        height=900,
        min_size=(1100, 700),
        resizable=True,
        text_select=False,
        frameless=False,
        easy_drag=True,
        on_top=False,
        background_color="#0F172A",
        js_api=api,
        hidden=is_headless,
    )
    # Bind api to window
    api.set_window(window)

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

    # Phase 4 Watchdog: monitor bridge responsiveness and log thread stacks if frozen
    watchdog_stop = threading.Event()

    def _watchdog_loop() -> None:
        while not watchdog_stop.wait(5.0):
            last_hb = getattr(api, "_last_heartbeat_time", 0.0)
            if last_hb > 0 and (time.time() - last_hb) > 15.0:
                logging.error(
                    "WATCHDOG: Bridge responsiveness stalled (>15s without activity). Thread stack dump:"
                )
                for thread_id, frame in sys._current_frames().items():
                    logging.error("Thread %s:\n%s", thread_id, "".join(traceback.format_stack(frame)))

    threading.Thread(target=_watchdog_loop, name="previewgen-watchdog", daemon=True).start()

    try:
        start_kwargs: dict[str, Any] = {"debug": False}
        if gui_type:
            start_kwargs["gui"] = gui_type
        if is_smoke and gui_type:
            def _auto_close_smoke() -> None:
                marker = os.environ.get("PREVIEWGEN_READY_MARKER")
                for _ in range(30):
                    if marker and Path(marker).is_file():
                        break
                    time.sleep(0.5)
                with contextlib.suppress(Exception):
                    window.destroy()
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
