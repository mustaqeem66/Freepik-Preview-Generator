"""
PreviewGen Desktop Runtime
Main entry point for the GUI application.
ONLY this module imports pywebview at module scope.
"""
from __future__ import annotations
import logging
import os
import sys
import tempfile
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

# THIS IS THE ONLY MODULE THAT IMPORTS WEBVIEW AT MODULE SCOPE
import webview

# Internal imports
from processor import (
    PreviewConfig,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_CAD_EXTENSIONS,
)
from previewgen.api import DesktopApi
from previewgen.settings import configure_logging
from previewgen.cli import cli_render_test, cli_render_test_all


def get_resource_dir() -> Path:
    """Get the resource directory for bundled assets."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore
    return Path(__file__).parent


def get_html_dist() -> Path:
    """Find the built frontend HTML bundle."""
    candidates = [
        get_resource_dir() / "frontend" / "dist" / "index.html",
        Path(__file__).parent / "frontend" / "dist" / "index.html",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


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
            cmd = f'display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK" with icon stop'
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
    if "--gui-smoke-test" in sys.argv:
        import os
        os.environ["PREVIEWGEN_READY_MARKER"] = os.environ.get("PREVIEWGEN_READY_MARKER", "")
        logging.info("GUI smoke test mode enabled")

    target_url = html_dist.as_uri()
    logging.info("Loading frontend from: %s", target_url)

    # Window creation
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
        hidden=False,
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
        is_local_packaged = target_base and (clean_url == target_base or clean_url.startswith(target_base))

        if is_dev or is_local_packaged:
            return True

        logging.warning("Blocked privileged window navigation to external origin: %s", url)
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            logging.debug("Could not open external URL: %s", e)
        return False

    try:
        window.events.navigating += on_navigating
    except Exception:
        pass

    try:
        webview.start(debug=False)
    except Exception as exc:
        show_fatal_error("PreviewGen - GUI Failure", f"Failed to initialize webview window: {exc}")
        raise
    finally:
        api.cleanup()
    
    return 0


def main() -> int:
    """
    Main entry point for PreviewGen.
    Handles CLI modes, smoke tests, and desktop application startup.
    """
    # Windows: suppress console output for frozen GUI apps
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(0xFFFFFFFF):  # ATTACH_PARENT_PROCESS
                try:
                    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                except Exception:
                    pass
        except Exception:
            pass

    # Configure logging first
    configure_logging()

    # --smoke-test: quick headless processor check (no GUI)
    if "--smoke-test" in sys.argv and "--gui-smoke-test" not in sys.argv:
        from processor import PreviewConfig, compose_preview, SUPPORTED_EXTENSIONS
        from PIL import Image
        html_dist = get_html_dist()
        assert html_dist.is_file(), f"Frontend bundle missing: {html_dist}"
        test_img = Image.new("RGBA", (100, 100), (99, 102, 241, 255))
        test_preview = compose_preview(test_img, PreviewConfig())
        assert test_preview.size == (100, 100)
        api = DesktopApi()
        api.cleanup()
        msg = f"[STARTUP-TEST] OK: PreviewGen initialized successfully. Bundle: {html_dist}, Formats: {len(SUPPORTED_EXTENSIONS)}"
        logging.info(msg)
        try:
            if sys.stdout is not None:
                sys.stdout.write(msg + "\n")
                sys.stdout.flush()
        except Exception:
            pass
        return 0

    # --render-test-all: CLI multi-format render test (no GUI)
    if "--render-test-all" in sys.argv:
        fixture_dir = "tests/fixtures"
        if "--fixtures" in sys.argv:
            idx = sys.argv.index("--fixtures")
            if idx + 1 < len(sys.argv):
                fixture_dir = sys.argv[idx + 1]
        return cli_render_test_all(fixture_dir)

    # --render-test: CLI render test (no GUI)
    if "--render-test" in sys.argv:
        return cli_render_test(*sys.argv[sys.argv.index("--render-test") + 1:])

    # Default: start desktop application
    return start_desktop_app()


if __name__ == "__main__":
    sys.exit(main())