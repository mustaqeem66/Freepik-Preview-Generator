"""
PreviewGen API Module
Python-side API exposed to frontend via pywebview.
Uses webview.Window type hints only (does not import webview at module scope).
"""
from __future__ import annotations
import base64
import json
import logging
import os
import shutil
import tempfile
import threading
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# Use TYPE_CHECKING to avoid runtime webview import
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import webview

from processor import (
    PreviewConfig,
    preview_jpeg_bytes,
    process_folder,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_CAD_EXTENSIONS,
)

from previewgen.scanner import get_scanner
from previewgen.settings import load_settings, save_settings, configure_logging, get_log_directory
from previewgen.lifecycle import LifecycleManager


class DesktopApi:
    """
    Main API exposed to the React frontend via pywebview.
    All GUI-dependent operations live here.
    """
    
    def __init__(self) -> None:
        self.window: Optional[Any] = None  # webview.Window when running
        self.session_zip_dir: Optional[Path] = None
        self.scanner = get_scanner()
        self.lifecycle = LifecycleManager()
        self.lifecycle.set_scanner(self.scanner)
        
        # Wire scanner callbacks to this API for JS dispatch
        self.scanner.set_callbacks(
            progress_callback=self._on_scan_progress,
            finished_callback=self._on_scan_finished,
        )
        self.lifecycle.set_batch_finished_callback(self._on_batch_finished)

    def set_window(self, win: Any) -> None:
        """Set the pywebview window reference."""
        self.window = win
        # Wire lifecycle scanner (already set)

    def _on_scan_progress(self, scan_id: str, count: int) -> None:
        """Dispatch scan progress to frontend."""
        if self.window:
            try:
                self.window.evaluate_js(f"window.__onScanProgress && window.__onScanProgress('{scan_id}', {count})")
            except Exception:
                pass

    def _on_scan_finished(self, scan_id: str, result: Dict[str, Any]) -> None:
        """Dispatch scan completion to frontend."""
        if self.window:
            try:
                payload_json = json.dumps(result)
                self.window.evaluate_js(f"window.__onScanFinished && window.__onScanFinished('{scan_id}', {payload_json})")
            except Exception as exc:
                logging.debug("Scan finished event dispatch notice: %s", exc)

    def _on_batch_finished(self, summary: Dict[str, Any]) -> None:
        """Dispatch batch completion to frontend."""
        if self.window:
            try:
                self.window.evaluate_js(f"window.__onBatchFinishedSummary({json.dumps(summary)})")
            except Exception:
                pass

    # ============================================================
    # Frontend-facing API methods
    # ============================================================

    def frontend_ready(self) -> Dict[str, Any]:
        """Called by React frontend when mounted and interactive."""
        logging.info("Frontend mounted and reported ready.")
        import os
        ready_marker = os.environ.get("PREVIEWGEN_READY_MARKER")
        if ready_marker:
            try:
                Path(ready_marker).write_text("READY\n", encoding="utf-8")
            except Exception as exc:
                logging.warning("Could not write ready marker: %s", exc)
        return {"ok": True, "value": "ready", "error": None}

    def get_initial_state(self) -> Dict[str, Any]:
        """Load persistent user preferences with schema version validation."""
        validated = load_settings()
        return {"ok": True, "value": validated, "error": None}

    def save_settings(self, settings_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Save user preferences atomically to disk with backup and schema version."""
        if not isinstance(settings_dict, dict):
            return {"ok": False, "value": False, "error": "Invalid settings payload"}
        try:
            if save_settings(settings_dict):
                return {"ok": True, "value": True, "error": None}
            else:
                return {"ok": False, "value": False, "error": "Atomic settings write failed"}
        except Exception as exc:
            logging.warning("Atomic settings write failed: %s", exc)
            return {"ok": False, "value": False, "error": str(exc)}

    def browse_input_folder(self) -> str:
        """Open native folder picker for input directory."""
        if not self.window:
            return ""
        try:
            res = self.window.create_file_dialog(int(__import__('webview').FOLDER_DIALOG))
            return res[0] if res else ""
        except Exception as exc:
            logging.warning("Folder dialog failed: %s", exc)
            return ""

    def browse_output_folder(self) -> str:
        """Open native folder picker for output directory."""
        if not self.window:
            return ""
        try:
            res = self.window.create_file_dialog(int(__import__('webview').FOLDER_DIALOG))
            return res[0] if res else ""
        except Exception as exc:
            logging.warning("Folder dialog failed: %s", exc)
            return ""

    def browse_logo(self) -> str:
        """Open native file picker for logo."""
        if not self.window:
            return ""
        try:
            res = self.window.create_file_dialog(
                int(__import__('webview').OPEN_DIALOG),
                file_types=("Image Files (*.png;*.webp;*.svg;*.ico;*.jpg;*.jpeg)", "*.png;*.webp;*.svg;*.ico;*.jpg;*.jpeg")
            )
            return res[0] if res else ""
        except Exception as exc:
            logging.warning("Logo dialog failed: %s", exc)
            return ""

    def browse_font(self) -> str:
        """Open native file picker for custom font."""
        if not self.window:
            return ""
        try:
            res = self.window.create_file_dialog(
                int(__import__('webview').OPEN_DIALOG),
                file_types=("Font Files (*.ttf;*.otf;*.woff;*.woff2)", "*.ttf;*.otf;*.woff;*.woff2")
            )
            return res[0] if res else ""
        except Exception as exc:
            logging.warning("Font dialog failed: %s", exc)
            return ""

    def open_folder(self, path: str) -> bool:
        """Open folder in native file explorer."""
        try:
            p = Path(path)
            if sys.platform == "win32":
                os.startfile(p)  # type: ignore
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", str(p)], check=False)
            else:
                import subprocess
                subprocess.run(["xdg-open", str(p)], check=False)
            return True
        except Exception:
            return False

    def scan_folder(self, folder_path: str) -> Dict[str, Any]:
        """Synchronous scan (used for initial load)."""
        return self.scanner.scan_folder(folder_path)

    def start_scan(self, folder_path: str) -> Dict[str, Any]:
        """Start background asynchronous folder scan."""
        return self.scanner.start_scan(folder_path)

    def cancel_scan(self) -> None:
        """Signal active folder scan to stop."""
        self.scanner.cancel_scan()

    def render_preview(self, file_path: str, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Render live preview asynchronously with strict config parsing."""
        temp_dir: Optional[Path] = None
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

            # Parse via strict PreviewConfig.from_mapping in preview mode
            cfg = PreviewConfig.from_mapping(config_dict, mode="preview")
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

    def start_batch(self, input_folder: str, output_folder: str, config_dict: Dict[str, Any]) -> None:
        """Start asynchronous batch processing on a dedicated worker thread."""
        if not self.window:
            return

        def on_progress(cur: int, tot: int, msg: str) -> None:
            if self.window:
                msg_json = json.dumps(str(msg))
                self.window.evaluate_js(f"window.__onBatchProgress({int(cur)}, {int(tot)}, {msg_json})")

        def run_worker() -> None:
            # Parse via strict-export mode for batch
            try:
                cfg = PreviewConfig.from_mapping(config_dict, mode="strict-export")
                cfg.position = "custom"
            except ValueError as val_err:
                logging.error("Strict export configuration validation failed: %s", val_err)
                if self.window:
                    fail_summary = {
                        "planned": 1,
                        "processed": 0,
                        "remaining": 1,
                        "success": 0,
                        "failed": 1,
                        "skipped": 0,
                        "cancelled": False,
                        "errors": [f"Configuration error: {val_err}"],
                        "duration": 0.0,
                    }
                    self.window.evaluate_js(f"window.__onBatchFinishedSummary({json.dumps(fail_summary)})")
                return

            try:
                summary = process_folder(
                    Path(input_folder),
                    Path(output_folder),
                    cfg,
                    on_progress,
                    self.cancel_event.is_set,
                )
                if self.window:
                    self.window.evaluate_js(f"window.__onBatchFinishedSummary({json.dumps(summary)})")
            except Exception as e:
                logging.exception("Batch execution failed")
                if self.window:
                    fail_summary = {
                        "planned": 1,
                        "processed": 0,
                        "remaining": 1,
                        "success": 0,
                        "failed": 1,
                        "skipped": 0,
                        "cancelled": False,
                        "errors": [str(e)],
                        "duration": 0.0,
                    }
                    self.window.evaluate_js(f"window.__onBatchFinishedSummary({json.dumps(fail_summary)})")

        self.cancel_event = threading.Event()
        self.batch_thread = threading.Thread(target=run_worker, daemon=True)
        self.batch_thread.start()

    def cancel_batch(self) -> None:
        """Cancel active batch processing."""
        self.cancel_event.set()

    def cleanup(self) -> None:
        """Orderly shutdown sequence."""
        self.lifecycle.cleanup()


# Note: Desktop shortcut management is the responsibility of system installers (Inno Setup / DMG / AppImage / setup scripts)
# Runtime auto-shortcut creation removed per security and packaging best practices.