"""
PreviewGen - Desktop Studio
Backend Engine for pywebview + React + Framer Motion
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import webview

from processor import (
    DEFAULT_TEXT,
    PreviewConfig,
    preview_jpeg_bytes,
    process_folder,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_CAD_EXTENSIONS,
)

SETTINGS_DIR = Path.home() / ".previewgen"
SETTINGS_FILE = SETTINGS_DIR / "settings.v1.json"
SETTINGS_BACKUP = SETTINGS_DIR / "settings.v1.json.bak"

if sys.platform.startswith("linux"):
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--no-sandbox" not in flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --no-sandbox".strip()

# On Windows, PyInstaller --noconsole sets sys.stdout/sys.stderr to invalid handles.
# If unhandled, writing or flushing during interpreter shutdown raises OSError 22.
if sys.platform == "win32" and getattr(sys, "frozen", False):
    import ctypes
    _attached = False
    try:
        if ctypes.windll.kernel32.AttachConsole(0xFFFFFFFF):  # ATTACH_PARENT_PROCESS
            _attached = True
    except Exception:
        pass

    if _attached:
        try:
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            _attached = False

    if not _attached:
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
        except Exception:
            sys.stdout = None
        try:
            sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
        except Exception:
            sys.stderr = None

import logging
from logging.handlers import RotatingFileHandler
import platform

def get_log_directory() -> Path:
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "PreviewGen" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "PreviewGen"
    return Path.home() / ".local" / "state" / "previewgen"


def configure_logging() -> Path:
    log_dir = get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "previewgen.log"
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handlers: list[logging.Handler] = [handler]
    # For frozen GUI apps on Windows without console, sys.stdout can be None or raise OSError 22 on write
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        if sys.stdout is not None:
            try:
                handlers.append(logging.StreamHandler(sys.stdout))
            except Exception:
                pass
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.info(
        "Starting PreviewGen platform=%s python=%s frozen=%s",
        platform.platform(),
        sys.version,
        getattr(sys, "frozen", False),
    )
    return log_file

# Note: Desktop shortcut management is the responsibility of system installers (Inno Setup / DMG / AppImage / setup scripts)
# Runtime auto-shortcut creation removed per security and packaging best practices.


def show_fatal_error(title: str, message: str) -> None:
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
class DesktopApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.session_zip_dir: Path | None = None
        self.cancel_event = threading.Event()
        self.batch_thread: threading.Thread | None = None

    def set_window(self, win: webview.Window) -> None:
        self.window = win

    def frontend_ready(self) -> dict[str, Any]:
        """Called by React frontend when mounted and interactive."""
        logging.info("Frontend mounted and reported ready.")
        ready_marker = os.environ.get("PREVIEWGEN_READY_MARKER")
        if ready_marker:
            try:
                Path(ready_marker).write_text("READY\n", encoding="utf-8")
            except Exception as exc:
                logging.warning("Could not write ready marker: %s", exc)
        if "--gui-smoke-test" in sys.argv:
            logging.info("GUI smoke test verified! Frontend interactive. Closing window.")
            threading.Thread(target=self._close_window_soon, daemon=True).start()
        return {"ok": True, "value": "ready", "error": None}

    def _close_window_soon(self) -> None:
        import time
        time.sleep(0.5)
        if self.window:
            self.window.destroy()

    def get_initial_state(self) -> dict[str, Any]:
        """Load persistent user preferences with atomic schema validation."""
        if SETTINGS_FILE.is_file():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Strip corrupted or unexpected top-level fields
                    clean_settings = {k: v for k, v in data.items() if isinstance(k, str) and not k.startswith("_")}
                    return {"ok": True, "value": clean_settings, "error": None}
            except Exception as exc:
                logging.warning("Primary settings corrupt: %s. Attempting backup.", exc)
                if SETTINGS_BACKUP.is_file():
                    try:
                        data = json.loads(SETTINGS_BACKUP.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            clean_settings = {k: v for k, v in data.items() if isinstance(k, str) and not k.startswith("_")}
                            return {"ok": True, "value": clean_settings, "error": None}
                    except Exception:
                        pass
        return {"ok": True, "value": {}, "error": None}

    def save_settings(self, settings_dict: dict[str, Any]) -> dict[str, Any]:
        """Save user preferences atomically to disk with backup and schema version."""
        if not isinstance(settings_dict, dict):
            return {"ok": False, "value": False, "error": "Invalid settings payload"}
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "_schema_version": 1,
                **{k: v for k, v in settings_dict.items() if isinstance(k, str) and not k.startswith("_")}
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
            return {"ok": True, "value": True, "error": None}
        except Exception as exc:
            logging.warning("Atomic settings write failed: %s", exc)
            return {"ok": False, "value": False, "error": str(exc)}

    def _powershell_folder_dialog(self, title: str = "Select Folder") -> str:
        if sys.platform != "win32":
            return ""
        try:
            cmd = (
                "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$f.Description = '{title}'; "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", cmd],
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            if out and Path(out).is_dir():
                return out
        except Exception as exc:
            logging.debug("PowerShell folder dialog fallback notice: %s", exc)
        return ""

    def _powershell_file_dialog(self, title: str, filter_str: str) -> str:
        if sys.platform != "win32":
            return ""
        try:
            cmd = (
                "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                f"$f.Title = '{title}'; "
                f"$f.Filter = '{filter_str}'; "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", cmd],
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            if out and Path(out).is_file():
                return out
        except Exception as exc:
            logging.debug("PowerShell file dialog fallback notice: %s", exc)
        return ""

    def browse_input_folder(self) -> str:
        """Open native OS folder selection dialog."""
        if self.window:
            try:
                res = self.window.create_file_dialog(int(webview.FOLDER_DIALOG))
                if res and len(res) > 0:
                    return res[0]
            except Exception as exc:
                logging.warning("pywebview folder dialog failed: %s", exc)
        return self._powershell_folder_dialog("Select Input Assets Folder")

    def browse_output_folder(self) -> str:
        """Open native OS folder selection dialog."""
        if self.window:
            try:
                res = self.window.create_file_dialog(int(webview.FOLDER_DIALOG))
                if res and len(res) > 0:
                    return res[0]
            except Exception as exc:
                logging.warning("pywebview output folder dialog failed: %s", exc)
        return self._powershell_folder_dialog("Select Output JPG Folder")

    def browse_logo(self) -> str:
        """Open native OS file selection dialog for logo images."""
        if self.window:
            try:
                res = self.window.create_file_dialog(
                    int(webview.OPEN_DIALOG),
                    file_types=("Logo Images (*.png;*.webp;*.svg;*.ico;*.jpg;*.jpeg)",),
                )
                if res and len(res) > 0:
                    return res[0]
            except Exception as exc:
                logging.warning("pywebview file dialog failed: %s", exc)
        return self._powershell_file_dialog("Select Logo Image", "Images (*.png;*.webp;*.svg;*.ico;*.jpg)|*.png;*.webp;*.svg;*.ico;*.jpg;*.jpeg|All Files (*.*)|*.*")

    def browse_font(self) -> str:
        """Open native OS file selection dialog for font files."""
        if self.window:
            try:
                res = self.window.create_file_dialog(
                    int(webview.OPEN_DIALOG),
                    file_types=("Font Files (*.ttf;*.otf;*.woff;*.woff2)",),
                )
                if res and len(res) > 0:
                    return res[0]
            except Exception as exc:
                logging.warning("pywebview font dialog failed: %s", exc)
        return self._powershell_file_dialog("Select Custom Brand Font", "Fonts (*.ttf;*.otf;*.woff;*.woff2)|*.ttf;*.otf;*.woff;*.woff2|All Files (*.*)|*.*")

    def open_folder(self, folder_path: str) -> bool:
        """Open the target directory in Windows Explorer / macOS Finder / Linux file manager."""
        p = Path(folder_path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return True
        except Exception:
            return False

    def scan_folder(self, folder_path: str) -> dict[str, Any]:
        """Scan folder for supported 2D and 3D assets, indexing zip files with quotas and depth bounds."""
        if not isinstance(folder_path, str) or not folder_path.strip():
            return {"files": [], "total": 0}

        p = Path(folder_path).resolve()
        if not p.is_dir():
            return {"files": [], "total": 0}

        # Clean prior session zip temp
        if self.session_zip_dir and self.session_zip_dir.exists():
            shutil.rmtree(self.session_zip_dir, ignore_errors=True)
            self.session_zip_dir = None

        files_payload: list[dict[str, Any]] = []
        MAX_SCANNED_ITEMS = 5000
        item_count = 0

        try:
            # Bounded traversal to prevent filesystem recursion loops and memory exhaustion
            for root, dirs, files in os.walk(p, topdown=True, followlinks=False):
                rel_root = Path(root).relative_to(p)
                # Skip hidden directories & macOS metadata
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d != "__MACOSX" and len(rel_root.parts) < 15
                ]
                for f_name in sorted(files):
                    if f_name.startswith(".") or f_name == "Thumbs.db":
                        continue
                    item_count += 1
                    if item_count > MAX_SCANNED_ITEMS:
                        logging.warning("Folder scan item cap (%d) reached at %s", MAX_SCANNED_ITEMS, root)
                        break
                    f_path = Path(root) / f_name
                    ext = f_path.suffix.lower()

                    if ext in SUPPORTED_EXTENSIONS and ext != ".zip":
                        ext_clean = ext.upper().lstrip(".")
                        is_3d = (ext in SUPPORTED_3D_EXTENSIONS and ext != ".blend") or ext in (".step", ".stp", ".iges", ".igs")
                        files_payload.append({
                            "name": f_path.name,
                            "path": str(f_path.resolve()),
                            "ext": ext_clean,
                            "is_3d": is_3d,
                        })
                    elif ext == ".zip":
                        # Bounded zip indexing
                        try:
                            import zipfile
                            with zipfile.ZipFile(f_path, "r") as zf:
                                members = zf.infolist()[:1000]  # Cap per archive
                                for member in members:
                                    if member.is_dir() or member.file_size > 250 * 1024 * 1024:
                                        continue
                                    member_path = Path(member.filename)
                                    clean_name = member_path.name
                                    if clean_name.startswith(".") or any(part == "__MACOSX" for part in member_path.parts):
                                        continue
                                    m_ext = member_path.suffix.lower()
                                    if m_ext in SUPPORTED_EXTENSIONS and m_ext != ".zip":
                                        m_clean = m_ext.upper().lstrip(".")
                                        m_3d = (m_ext in SUPPORTED_3D_EXTENSIONS and m_ext != ".blend") or m_ext in (".step", ".stp", ".iges", ".igs")
                                        files_payload.append({
                                            "name": f"{f_path.stem}/{clean_name}",
                                            "path": f"zip://{f_path.resolve()}?entry={member.filename}",
                                            "ext": m_clean,
                                            "is_3d": m_3d,
                                        })
                                        item_count += 1
                                        if item_count > MAX_SCANNED_ITEMS:
                                            break
                        except Exception as exc:
                            logging.warning("Could not index archive %s: %s", f_path.name, exc)

                if item_count > MAX_SCANNED_ITEMS:
                    break
        except Exception as exc:
            logging.warning("Folder scan interrupted: %s", exc)

        return {"files": files_payload, "total": len(files_payload)}
    def render_preview(self, file_path: str, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Render live preview asynchronously with strict config parsing and structured envelope."""
        temp_dir: Path | None = None
        try:
            if not isinstance(file_path, str) or not file_path.strip():
                return {"ok": False, "value": None, "error": "Empty file path"}

            if file_path.startswith("zip://"):
                import urllib.parse
                import zipfile
                parsed = urllib.parse.urlparse(file_path)
                zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                qs = urllib.parse.parse_qs(parsed.query)
                entry_name = qs.get("entry", [""])[0]
                if not zip_path.is_file() or not entry_name:
                    return {"ok": False, "value": None, "error": "Invalid zip entry URI"}
                temp_dir = Path(tempfile.mkdtemp(prefix="previewgen_ondemand_"))
                target_file = temp_dir / Path(entry_name).name
                with zipfile.ZipFile(zip_path, "r") as zf:
                    with zf.open(entry_name) as src, open(target_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                source_path = target_file
            else:
                source_path = Path(file_path).resolve()

            if not source_path.is_file():
                return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            # Parse via strict PreviewConfig.from_mapping
            cfg = PreviewConfig.from_mapping(config_dict)
            cfg.position = "custom"

            jpeg_bytes, orig_w, orig_h = preview_jpeg_bytes(source_path, cfg, max_dimension=850)
            b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            return {
                "ok": True,
                "value": {
                    "dataUrl": f"data:image/jpeg;base64,{b64}",
                    "width": orig_w,
                    "height": orig_h,
                },
                "error": None,
            }
        except Exception as exc:
            logging.warning("render_preview failure: %s", exc)
            return {"ok": False, "value": None, "error": str(exc)}
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
    def start_batch(self, input_folder: str, output_folder: str, config_dict: dict[str, Any]) -> None:
        """Start asynchronous batch processing on a dedicated worker thread."""
        if self.batch_thread and self.batch_thread.is_alive():
            logging.warning("Batch processing already active; ignoring duplicate request.")
            return

        self.cancel_event.clear()

        cfg = PreviewConfig.from_mapping(config_dict)
        cfg.position = "custom"

        def run_worker() -> None:
            def on_progress(cur: int, tot: int, msg: str) -> None:
                if self.window:
                    msg_json = json.dumps(str(msg))
                    self.window.evaluate_js(f"window.__onBatchProgress({int(cur)}, {int(tot)}, {msg_json})")
            try:
                # Disk space preflight check (at least 200 MB free)
                out_p = Path(output_folder).resolve()
                out_p.mkdir(parents=True, exist_ok=True)
                free_bytes = shutil.disk_usage(out_p).free
                if free_bytes < 200 * 1024 * 1024:
                    raise RuntimeError(f"Insufficient disk space on target volume: {free_bytes // (1024*1024)} MB available (200 MB required).")

                summary = process_folder(
                    Path(input_folder),
                    out_p,
                    cfg,
                    on_progress,
                    self.cancel_event.is_set,
                )

                # Save persistent batch summary and error report in output folder
                try:
                    report_file = out_p / "previewgen_batch_report.json"
                    report_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                except Exception as r_err:
                    logging.warning("Could not write batch report file: %s", r_err)

                if self.window:
                    summary_json = json.dumps(summary)
                    self.window.evaluate_js(f"window.__onBatchFinishedSummary({summary_json})")
            except Exception as e:
                logging.exception("Batch execution failed")
                if self.window:
                    fail_summary = {
                        "planned": 1,
                        "processed": 0,
                        "success": 0,
                        "failed": 1,
                        "skipped": 0,
                        "cancelled": False,
                        "errors": [str(e)],
                        "duration": 0.0,
                    }
                    fail_json = json.dumps(fail_summary)
                    self.window.evaluate_js(f"window.__onBatchFinishedSummary({fail_json})")

        self.batch_thread = threading.Thread(target=run_worker, daemon=True)
        self.batch_thread.start()
    def cancel_batch(self) -> None:
        self.cancel_event.set()

    def cleanup(self) -> None:
        if self.session_zip_dir and self.session_zip_dir.exists():
            shutil.rmtree(self.session_zip_dir, ignore_errors=True)


def main() -> int:
    log_file = configure_logging()
# Desktop shortcut ensure removed
    is_frozen = getattr(sys, "frozen", False)
    dev_mode = os.environ.get("PREVIEWGEN_DEV") == "1"

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MustaqeemTools.PreviewGen.App.1.0")
        except Exception:
            pass

    # Determine HTML entry path (handles frozen bundle, source dev, and production dist)
    if is_frozen:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()
    else:
        base_dir = Path(__file__).resolve().parent

    candidates = [
        base_dir / "frontend" / "dist" / "index.html",
        base_dir / "dist" / "index.html",
        base_dir / "index.html",
    ]
    if is_frozen:
        candidates.insert(0, Path(sys.executable).resolve().parent / "frontend" / "dist" / "index.html")
        candidates.insert(1, Path(sys.executable).resolve().parent / "dist" / "index.html")

    html_dist: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            html_dist = candidate
            break

    target_url: str | None = None
    if html_dist and html_dist.is_file():
        target_url = html_dist.resolve().as_uri()
        logging.info("Loaded frontend bundle from %s", html_dist)
    elif not is_frozen and dev_mode:
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:5173", timeout=0.5)
            target_url = "http://localhost:5173"
            logging.info("Development mode active: bound to Vite server http://localhost:5173")
        except Exception:
            target_url = None

    if "--smoke-test" in sys.argv and "--gui-smoke-test" not in sys.argv:
        from processor import PreviewConfig, compose_preview, SUPPORTED_EXTENSIONS
        from PIL import Image
        assert html_dist is not None and html_dist.is_file(), f"Frontend bundle missing: {candidates}"
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

    if not target_url:
        err_msg = (
            "PreviewGen could not locate its required frontend bundle.\n\n"
            f"Search path: {base_dir}\n"
            "Expected file: frontend/dist/index.html\n\n"
            "Please reinstall PreviewGen or run 'npm run build' in the frontend directory."
        )
        show_fatal_error("PreviewGen - Missing Assets", err_msg)
        raise RuntimeError(err_msg)

    api = DesktopApi()
    window = webview.create_window(
        title="PreviewGen",
        url=target_url,
        js_api=api,
        width=1340,
        height=900,
        min_size=(1020, 720),
        background_color="#D6E6EF",
    )
    if window is not None:
        api.set_window(window)

    # P0-3: Explicit navigation lockdown to packaged local HTML
    # Block navigation away from target_url and launch external links in native OS browser
    def on_navigating(url: str) -> None:
        if not url:
            return
        target_base = target_url.split("#")[0].split("?")[0].rstrip("/") if target_url else ""
        clean_url = url.split("#")[0].split("?")[0].rstrip("/")
        if target_base and clean_url != target_base:
            logging.warning("Prevented privileged window navigation to external origin: %s", url)
            import webbrowser
            try:
                webbrowser.open(url)
            except Exception as e:
                logging.debug("Could not open external URL: %s", e)

    if window is not None:
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


if __name__ == "__main__":
    raise SystemExit(main())
