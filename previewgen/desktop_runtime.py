"""
PreviewGen Desktop Runtime
GUI entry point. ONLY this module imports pywebview, and it does so inside the guarded startup path.

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

from previewgen.api import DesktopApi
from previewgen.dialogs import applescript_string
from previewgen.linux_webkit import configure_linux_webkit_runtime
from previewgen.resources import get_html_dist, get_resource_dir
from previewgen.ui_watchdog import WindowHangDetector, log_thread_stacks, windows_window_responding

# Smoke mode gives the frontend time to report ready, then closes the window and
# exits 0 regardless; only the ready marker separates a hung injection from a
# clean run, so that is what the packaged CI gates assert on.
#
# The ready budget covers the frontend mount only and is spent from the moment
# the process starts, because a frontend that never mounts must still time
# out. The CSP self-test budget is additional and is spent from the moment the
# frontend reports ready: the probe itself needs up to 8s in a live WebView,
# and counting that time against the mount budget let a slow macOS mount
# destroy the window mid-probe and lose the verdict.
SMOKE_READY_POLL_ATTEMPTS = 30
SMOKE_READY_POLL_SECONDS = 0.5
# The probe itself polls for at most 8s inside a live WebView. This wait is
# the outer guard for the file it writes, so it only needs enough room for
# that probe plus the round trip of writing the marker.
SMOKE_CSP_POLL_ATTEMPTS = 40
SMOKE_CSP_POLL_SECONDS = 0.5


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
                f'{applescript_string(title)} buttons {{"OK"}} default button "OK" with icon stop'
            )
            result = subprocess.run(["osascript", "-e", cmd], check=False, timeout=30)
            if result.returncode == 0:
                return
        except Exception:
            pass
    stream = sys.stderr
    if stream is not None:
        with contextlib.suppress(Exception):
            stream.write(f"\n[FATAL ERROR] {title}\n{message}\n\n")


def bridge_is_stalled(api: Any, now: float, quiet_seconds: float = 15.0) -> bool:
    """True when the bridge has emitted nothing for ``quiet_seconds`` during work.

    Heartbeats only advance when Python pushes an event, so a quiet bridge with
    nothing in flight is an idle app, not a frozen one.
    """
    last_hb = getattr(api, "_last_heartbeat_time", 0.0)
    if last_hb <= 0 or (now - last_hb) <= quiet_seconds:
        return False
    return bool(api.has_outstanding_work())


def _create_desktop_window(
    html_dist: Path,
    *,
    is_smoke: bool,
    custom_chrome: bool,
) -> tuple[Any | None, Any | None]:
    """Create the native API and window inside one fail-closed boundary."""
    api: Any | None = None
    try:
        # Import the native backend only after the fatal-error handler exists.
        # A damaged frozen PyObjC/WebKit package must reach that handler rather
        # than terminating a windowed .app while the module is being imported.
        import webview

        api = DesktopApi()
        window = webview.create_window(
            "PreviewGen",
            html_dist.as_uri(),
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
            hidden=is_smoke,
        )
        if window is None:
            raise RuntimeError("webview.create_window returned no window; a GUI backend is unavailable")
        return api, window
    except Exception as exc:
        if api is not None:
            with contextlib.suppress(Exception):
                api.cleanup()
        show_fatal_error(
            "PreviewGen - GUI Failure",
            f"Failed to initialize webview window: {exc}",
        )
        return None, None


def start_desktop_app() -> int:
    """
    Create and run the pywebview window with the React frontend.
    This is the ONLY function that creates a webview window.

    Returns:
        Exit code (0 on success, non-zero on failure)
    """
    logging.info("Starting PreviewGen desktop runtime...")

    try:
        html_dist = get_html_dist()
    except Exception as exc:
        show_fatal_error(
            "PreviewGen - GUI Failure",
            f"Failed to locate the frontend bundle: {exc}",
        )
        return 1

    if not html_dist.is_file():
        show_fatal_error(
            "PreviewGen - Missing Frontend Bundle",
            f"Cannot find frontend bundle at: {html_dist}\n\nPlease reinstall PreviewGen.",
        )
        return 1

    # A frozen Linux build must select its matching WebKitGTK injected bundle
    # before pywebview creates the window and starts WebKit child processes.
    try:
        configure_linux_webkit_runtime(
            get_resource_dir(),
            platform=sys.platform,
            environ=os.environ,
            frozen=bool(getattr(sys, "frozen", False)),
        )
    except RuntimeError as exc:
        show_fatal_error("PreviewGen - Incompatible WebKitGTK Runtime", str(exc))
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

    # Set PREVIEWGEN_NATIVE_TITLEBAR=1 to fall back to OS decorations on
    # systems where frameless windows are not draggable/resizable.
    custom_chrome = os.environ.get("PREVIEWGEN_NATIVE_TITLEBAR") != "1"
    api, window = _create_desktop_window(
        html_dist,
        is_smoke=is_smoke,
        custom_chrome=custom_chrome,
    )
    if api is None or window is None:
        return 1
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
                    log_thread_stacks("Backend operation active but no outgoing bridge events for >15s")
            except Exception:
                logging.debug("UI watchdog probe failed", exc_info=True)

    threading.Thread(
        target=_watchdog_loop,
        name="previewgen-ui-watchdog",
        daemon=True,
    ).start()

    try:
        import webview

        start_kwargs: dict[str, Any] = {"debug": False}
        if gui_type:
            start_kwargs["gui"] = gui_type
        if is_smoke and gui_type:

            def _auto_close_smoke(smoke_window: Any = window) -> None:
                marker = os.environ.get("PREVIEWGEN_READY_MARKER")
                # When the CSP self-test is enabled it needs a live WebView to
                # run in, so the window must outlive the ready marker until the
                # self-test has written its result. That wait gets its own
                # budget, counted from the moment the frontend reports ready,
                # so a slow frontend mount cannot starve the probe.
                csp_marker = os.environ.get("PREVIEWGEN_CSP_MARKER")
                ready_seen = False
                for _ in range(SMOKE_READY_POLL_ATTEMPTS):
                    if marker and Path(marker).is_file():
                        ready_seen = True
                        break
                    time.sleep(SMOKE_READY_POLL_SECONDS)
                # The probe only starts once the frontend has reported ready, so
                # there is nothing to wait for when the mount never happened.
                if csp_marker and ready_seen:
                    for _ in range(SMOKE_CSP_POLL_ATTEMPTS):
                        if Path(csp_marker).is_file():
                            break
                        time.sleep(SMOKE_CSP_POLL_SECONDS)
                    else:
                        # The probe did not write its verdict inside its
                        # budget. Dump every thread's stack so the failure
                        # says where the probe is stuck instead of only
                        # reporting a missing marker.
                        log_thread_stacks("the CSP smoke probe did not finish in time")
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
        return 1
    finally:
        watchdog_stop.set()
        with contextlib.suppress(Exception):
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
