"""
PreviewGen Entry Point
GUI-independent argument dispatch.

pywebview is imported lazily and only when the desktop GUI is actually started,
so CLI modes (--render-test, --render-test-all, --list-formats), the headless
--smoke-test, and pure tests never require the GUI runtime.
"""
from __future__ import annotations

import logging
import sys


def _reattach_windows_console() -> None:
    """Windows: reattach stdout/stderr for frozen GUI apps when a console exists."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes
        windll = getattr(ctypes, "windll", None)
        if windll is not None and windll.kernel32.AttachConsole(0xFFFFFFFF):  # ATTACH_PARENT_PROCESS
            try:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
            except Exception:
                pass
    except Exception:
        pass


def _run_headless_smoke_test() -> int:
    """Quick headless processor check (no GUI)."""
    from PIL import Image

    from previewgen.api import DesktopApi
    from previewgen.resources import get_html_dist
    from processor import SUPPORTED_EXTENSIONS, PreviewConfig, compose_preview

    html_dist = get_html_dist()
    assert html_dist.is_file(), f"Frontend bundle missing: {html_dist}"
    test_img = Image.new("RGBA", (100, 100), (99, 102, 241, 255))
    test_preview = compose_preview(test_img, PreviewConfig())
    assert test_preview.size == (100, 100)
    api = DesktopApi()
    api.cleanup()
    msg = (
        f"[STARTUP-TEST] OK: PreviewGen initialized successfully. "
        f"Bundle: {html_dist}, Formats: {len(SUPPORTED_EXTENSIONS)}"
    )
    logging.info(msg)
    try:
        if sys.stdout is not None:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()
    except Exception:
        pass
    return 0


def main() -> int:
    """
    Main entry point for PreviewGen.
    Handles CLI modes, smoke tests, and (lazily) desktop application startup.
    """
    # Required for multiprocessing (isolated renderer children) inside a
    # PyInstaller-frozen executable on Windows/macOS. Harmless otherwise.
    import multiprocessing
    multiprocessing.freeze_support()

    _reattach_windows_console()

    from previewgen.settings import configure_logging
    configure_logging()

    # Temp sweeps can traverse slow antivirus/network-backed directories. Never
    # run unbounded filesystem deletion on the desktop startup path.
    def _cleanup_stale_async() -> None:
        try:
            from previewgen.tempfiles import cleanup_stale_temp_dirs
            cleanup_stale_temp_dirs()
        except Exception as exc:
            logging.debug("Startup stale temp cleanup skipped: %s", exc)

    import threading
    threading.Thread(
        target=_cleanup_stale_async, name="previewgen-startup-cleanup", daemon=True,
    ).start()

    args = sys.argv[1:]

    # --smoke-test: quick headless processor check (no GUI)
    if "--smoke-test" in args and "--gui-smoke-test" not in args:
        return _run_headless_smoke_test()

    # --render-test / --render-test-all: CLI render tests (no GUI). Delegated to
    # main_cli so flags such as --fixtures and --size are parsed consistently.
    if "--render-test-all" in args or "--render-test" in args:
        from previewgen.cli import main_cli
        return main_cli(args)

    if "--list-formats" in args:
        from previewgen.cli import cli_list_formats
        return cli_list_formats()

    if "--help" in args or "-h" in args:
        from previewgen.cli import main_cli
        return main_cli([])

    # Default: start the desktop GUI. pywebview is imported only here.
    from previewgen.desktop_runtime import start_desktop_app
    return start_desktop_app()


if __name__ == "__main__":
    sys.exit(main())
