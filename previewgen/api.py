"""
PreviewGen API Module
Python-side API exposed to frontend via pywebview.
Uses webview.Window type hints only (does not import webview at module scope).
"""
from __future__ import annotations

import contextlib
import itertools
import json
import logging
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path

# Use TYPE_CHECKING to avoid runtime webview import
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from previewgen import limits
from previewgen.assets import calculate_export_dimensions as _calc_export_dimensions
from previewgen.lifecycle import ActiveOperation, LifecycleManager
from previewgen.preview_coordinator import PreviewCoordinator
from previewgen.preview_server import PreviewFileServer
from previewgen.probe_coordinator import ProbeCoordinator
from previewgen.probe_process import probe_asset_isolated
from previewgen.scanner import get_scanner
from previewgen.settings import load_settings, save_settings
from previewgen.tempfiles import safe_rmtree
from processor import (
    PreviewConfig,
    preview_jpeg_bytes,
    process_folder,
)


class DesktopApi:
    """
    Main API exposed to the React frontend via pywebview.
    All GUI-dependent operations live here.
    """

    def __init__(self) -> None:
        self.window: Any | None = None  # webview.Window when running
        self.session_zip_dir: Path | None = None
        self.scanner = get_scanner()
        self.lifecycle = LifecycleManager()
        self.lifecycle.set_scanner(self.scanner)
        self.preview_server = PreviewFileServer()
        self.preview_coordinator = PreviewCoordinator(self.preview_server)
        self.preview_coordinator.set_dispatch_fn(self._dispatch_envelope)
        self.probe_coordinator = ProbeCoordinator()
        self.probe_coordinator.set_dispatch_fn(self._dispatch_envelope)
        self._preview_request_lock = threading.Lock()
        self._latest_preview_request_id = 0
        self._batch_start_lock = threading.Lock()
        self._batch_operation_id = ""
        self._sequence_counter = itertools.count(1)
        self._authorized_folders: set[Path] = set()
        self._register_default_authorized_paths()

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

    def _register_default_authorized_paths(self) -> None:
        from previewgen.settings import get_log_directory, get_settings_directory
        self.add_authorized_folder(get_settings_directory())
        self.add_authorized_folder(get_log_directory())

    def add_authorized_folder(self, folder: Path | str) -> None:
        with contextlib.suppress(Exception):
            self._authorized_folders.add(Path(folder).resolve())

    def is_authorized_path(self, path: Path | str) -> bool:
        try:
            target = Path(path).resolve()
            for auth in self._authorized_folders:
                try:
                    target.relative_to(auth)
                    return True
                except ValueError:
                    continue
            return False
        except Exception:
            return False

    def _dispatch_envelope(
        self, event_name: str, payload: dict[str, Any], operation_id: str = "", terminal: bool = False
    ) -> None:
        """Send one serialized event envelope to the single frontend bridge receiver.

        Python never assembles per-event JavaScript or knows per-event global
        names; it emits the same ``{event, operationId, sequence, terminal,
        payload}`` envelope consumed by the frontend typed event hub. ``terminal``
        marks the final event of an operation so the frontend can reject any
        non-terminal event that arrives late for a completed operation.
        """
        if not self.window:
            return
        seq = next(self._sequence_counter)
        op_id = operation_id or self._batch_operation_id or payload.get("scanId") or f"op_{seq}"
        envelope = {
            "event": event_name,
            "operationId": op_id,
            "sequence": seq,
            "terminal": terminal,
            "payload": payload,
        }
        script = f"window.__onBridgeEvent && window.__onBridgeEvent({json.dumps(envelope)})"
        with contextlib.suppress(Exception):
            self.window.evaluate_js(script)

    def _on_scan_progress(self, scan_id: str, count: int) -> None:
        self._dispatch_envelope("scan.progress", {"scanId": scan_id, "count": count}, operation_id=scan_id)

    def _on_scan_finished(self, scan_id: str, result: dict[str, Any]) -> None:
        self._dispatch_envelope(
            "scan.finished", {"scanId": scan_id, "result": result}, operation_id=scan_id, terminal=True
        )

    def _on_batch_finished(self, summary: dict[str, Any]) -> None:
        self._dispatch_envelope(
            "batch.finished", summary, operation_id=self._batch_operation_id, terminal=True
        )
    # ============================================================
    # Frontend-facing API methods
    # ============================================================

    def frontend_ready(self) -> dict[str, Any]:
        """Called by React frontend when mounted and interactive."""
        logging.info("Frontend mounted and reported ready.")
        ready_marker = os.environ.get("PREVIEWGEN_READY_MARKER")
        if ready_marker:
            try:
                Path(ready_marker).write_text("READY\n", encoding="utf-8")
            except Exception as exc:
                logging.warning("Could not write ready marker: %s", exc)
        if "--gui-smoke-test" in sys.argv and self.window:
            # Destroy window after bridge response completes so clean machine tests exit promptly
            threading.Timer(0.5, self.window.destroy).start()
        return {"ok": True, "value": "ready", "error": None}
    def get_initial_state(self) -> dict[str, Any]:
        """Load persistent user preferences with schema version validation."""
        validated = load_settings()
        return {"ok": True, "value": validated, "error": None}

    def save_settings(self, settings_dict: dict[str, Any]) -> dict[str, Any]:
        """Save user preferences atomically to disk with backup and schema version."""
        if not isinstance(settings_dict, dict):
            return {"ok": False, "value": False, "error": "Invalid settings payload"}
        try:
            if save_settings(settings_dict):
                return {"ok": True, "value": True, "error": None}
            else:
                from previewgen.settings import get_current_revision
                curr_rev = get_current_revision()
                req_rev = settings_dict.get("revision")
                if req_rev is not None and isinstance(req_rev, (int, float)) and req_rev < curr_rev:
                    msg = f"Stale settings write (rev {req_rev} < current {curr_rev})"
                    return {"ok": False, "value": False, "error": msg}
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
                file_types=(
                    "Image Files (*.png;*.webp;*.svg;*.ico;*.jpg;*.jpeg)",
                    "*.png;*.webp;*.svg;*.ico;*.jpg;*.jpeg",
                )
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

    def open_folder(self, path: str) -> dict[str, Any]:
        """Open folder in native file explorer with path authorization checks."""
        if not isinstance(path, str) or not path.strip():
            return {"ok": False, "error": "EMPTY_PATH"}
        try:
            target = Path(path).resolve()
            if not self.is_authorized_path(target):
                return {"ok": False, "error": "UNAUTHORIZED_PATH"}
            if not target.is_dir():
                return {"ok": False, "error": "FOLDER_NOT_FOUND"}
            if sys.platform == "win32":
                os.startfile(target)  # type: ignore
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(
                    ["open", str(target)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            else:
                import subprocess
                subprocess.Popen(
                    ["xdg-open", str(target)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return {"ok": True, "error": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def scan_folder(self, folder_path: str) -> dict[str, Any]:
        """Synchronous scan (used for initial load)."""
        return self.scanner.scan_folder(folder_path)

    def start_scan(self, folder_path: str) -> dict[str, Any]:
        """Start background asynchronous folder scan."""
        return self.scanner.start_scan(folder_path)

    def cancel_scan(self) -> None:
        """Signal active folder scan to stop."""
        self.scanner.cancel_scan()

    def start_preview(
        self, file_path: str, config_dict: dict[str, Any], request_id: int | None = None
    ) -> dict[str, Any]:
        """
        Asynchronous preview request (P0 fix: non-blocking control plane).
        Validates request parameters immediately without decoding, rendering, or
        extracting any archive member, submits the latest request to the isolated
        worker, and returns right away. Results are dispatched via the typed event
        envelope: preview.completed / preview.failed.
        """
        if not isinstance(file_path, str) or not file_path.strip():
            return {"ok": False, "error": "Empty file path"}

        op_id = f"preview_{request_id or uuid.uuid4().hex[:6]}"
        try:
            # Cheap synchronous validation only. Archive members are extracted on
            # the worker thread so a large zip:// member never blocks the bridge.
            if file_path.startswith("zip://"):
                import urllib.parse
                parsed = urllib.parse.urlparse(file_path)
                zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                if not zip_path.is_file() or not entry_name:
                    return {"ok": False, "error": "Invalid zip entry URI"}
            else:
                source_path = Path(file_path).resolve()
                if not source_path.is_file():
                    return {"ok": False, "error": f"File does not exist: {source_path.name}"}

            self.preview_coordinator.submit_preview(
                operation_id=op_id,
                source=file_path,
                config_dict=config_dict,
                max_dimension=850,
            )
            return {"ok": True, "operationId": op_id, "status": "queued"}
        except Exception as exc:
            logging.warning("start_preview submission notice: %s", exc)
            return {"ok": False, "error": str(exc)}

    def cancel_preview(self, operation_id: str | None = None) -> dict[str, Any]:
        """Cancel running and queued live preview generation."""
        self.preview_coordinator.cancel_active(operation_id)
        return {"ok": True}

    def render_preview(
        self, file_path: str, config_dict: dict[str, Any], request_id: int | None = None
    ) -> dict[str, Any]:
        """Synchronous preview fallback retained strictly for test/CLI compatibility."""
        op_id = f"render_preview_{request_id or uuid.uuid4().hex[:6]}"
        op = ActiveOperation(operation_id=op_id, kind="preview_render")
        self.lifecycle.register_operation(op)
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
                op.temp_roots.add(temp_dir)
                target_file = temp_dir / Path(entry_name).name
                with zipfile.ZipFile(zip_path, "r") as zf:
                    limits.extract_zip_member_bounded(zf, entry_name, target_file)
                source_path = target_file
            else:
                source_path = Path(file_path).resolve()

            if not source_path.is_file():
                return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            cfg = PreviewConfig.from_mapping(config_dict, mode="preview")
            cfg.position = "custom"

            jpeg_bytes, orig_w, orig_h = preview_jpeg_bytes(source_path, cfg, max_dimension=850)
            preview_url = self.preview_server.publish_jpeg(jpeg_bytes)
            preview_id = preview_url.split("/")[-1] if "/" in preview_url else preview_url
            return {
                "ok": True,
                "value": {
                    "url": preview_url,
                    "previewId": preview_id,
                    "width": orig_w,
                    "height": orig_h,
                },
                "error": None,
            }
        except Exception as exc:
            logging.warning("render_preview failure: %s", exc)
            from previewgen.errors import classify_exception
            code, msg = classify_exception(exc)
            return {"ok": False, "value": None, "error": msg, "code": code}
        finally:
            self.lifecycle.unregister_operation(op_id)
            if temp_dir and temp_dir.exists():
                safe_rmtree(temp_dir, "on-demand preview temp", operation_id=op_id)
    def release_preview(self, handle: str) -> dict[str, Any]:
        """Release a preview handle and reclaim storage."""
        if not isinstance(handle, str) or not handle.strip():
            return {"ok": False, "value": False, "error": "Empty preview handle"}
        removed = self.preview_server.release_jpeg(handle, force=True)
        return {"ok": True, "value": removed, "error": None}


    def start_probe(self, file_path: str, request_id: int | None = None) -> dict[str, Any]:
        """
        Asynchronous asset probe request (P0 fix: non-blocking control plane).
        Validates path immediately, submits to isolated probe coordinator, and returns.
        Results are dispatched via typed event envelope: probe.completed / probe.failed.
        """
        if not isinstance(file_path, str) or not file_path.strip():
            return {"ok": False, "error": "Empty file path"}

        op_id = f"probe_{request_id or uuid.uuid4().hex[:6]}"
        try:
            if file_path.startswith("zip://"):
                import urllib.parse
                parsed = urllib.parse.urlparse(file_path)
                zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                if not zip_path.is_file() or not entry_name:
                    return {"ok": False, "error": "Invalid zip entry URI"}
            else:
                source_path = Path(file_path).resolve()
                if not source_path.is_file():
                    return {"ok": False, "error": f"File does not exist: {source_path.name}"}

            self.probe_coordinator.submit_probe(
                operation_id=op_id,
                source=file_path,
            )
            return {"ok": True, "operationId": op_id, "status": "queued"}
        except Exception as exc:
            logging.warning("start_probe submission notice: %s", exc)
            return {"ok": False, "error": str(exc)}
    def cancel_probe(self, operation_id: str | None = None) -> dict[str, Any]:
        """Cancel running and queued asset probing."""
        self.probe_coordinator.cancel_active(operation_id)
        return {"ok": True}

    def probe_asset(self, file_path: str, request_id: int | None = None) -> dict[str, Any]:
        """Synchronous asset probe fallback retained for test/CLI compatibility."""
        op_id = f"probe_{request_id or uuid.uuid4().hex[:6]}"
        op = ActiveOperation(operation_id=op_id, kind="asset_probe")
        self.lifecycle.register_operation(op)
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
                temp_dir = Path(tempfile.mkdtemp(prefix="previewgen_probe_"))
                op.temp_roots.add(temp_dir)
                target_file = temp_dir / Path(entry_name).name
                with zipfile.ZipFile(zip_path, "r") as zf:
                    limits.extract_zip_member_bounded(zf, entry_name, target_file)
                source_path = target_file
            else:
                source_path = Path(file_path).resolve()

            if not source_path.is_file():
                return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            probe_data = probe_asset_isolated(source_path)
            if request_id is not None:
                probe_data["requestId"] = request_id
            return {"ok": True, "value": probe_data, "error": None}
        except Exception as exc:
            logging.warning("probe_asset failure: %s", exc)
            from previewgen.errors import classify_exception
            code, msg = classify_exception(exc)
            return {"ok": False, "value": None, "error": msg, "code": code}
        finally:
            self.lifecycle.unregister_operation(op_id)
            if temp_dir and temp_dir.exists():
                safe_rmtree(temp_dir, "on-demand probe temp", operation_id=op_id)

    def calculate_export_dimensions(
        self, file_path: str, requested_width: int = 0, requested_height: int = 0
    ) -> dict[str, Any]:
        """Expose canonical export-dimension calculations to eliminate frontend/backend drift."""
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
                temp_dir = Path(tempfile.mkdtemp(prefix="previewgen_dim_"))
                target_file = temp_dir / Path(entry_name).name
                with zipfile.ZipFile(zip_path, "r") as zf:
                    limits.extract_zip_member_bounded(zf, entry_name, target_file)
                source_path = target_file
            else:
                source_path = Path(file_path).resolve()

            if not source_path.is_file():
                return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            dims = _calc_export_dimensions(
                source_path, requested_width=requested_width, requested_height=requested_height
            )
            return {"ok": True, "value": dims, "error": None}
        except Exception as exc:
            logging.warning("calculate_export_dimensions failure: %s", exc)
            from previewgen.errors import classify_exception
            code, msg = classify_exception(exc)
            return {"ok": False, "value": None, "error": msg, "code": code}
        finally:
            if temp_dir and temp_dir.exists():
                safe_rmtree(temp_dir, "on-demand dimension temp")
    def export_preview(self, file_path: str, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Render a single asset to a JPG at the configured export size."""
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
                temp_dir = Path(tempfile.mkdtemp(prefix="previewgen_export_"))
                target_file = temp_dir / Path(entry_name).name
                with zipfile.ZipFile(zip_path, "r") as zf:
                    limits.extract_zip_member_bounded(zf, entry_name, target_file)
                source_path = target_file
            else:
                source_path = Path(file_path).resolve()

            if not source_path.is_file():
                return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            cfg = PreviewConfig.from_mapping(config_dict, mode="strict-export")
            out_dir = Path(config_dict.get("outputFolder") or source_path.parent).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            self.add_authorized_folder(out_dir)

            from processor import generate_file
            dest_file = out_dir / f"{source_path.stem}.jpg"
            generate_file(source_path, dest_file, cfg)
            if not dest_file.is_file() or dest_file.stat().st_size == 0:
                return {"ok": False, "value": None, "error": "Export failed"}

            from PIL import Image
            with Image.open(dest_file) as im:
                w, h = im.size

            return {
                "ok": True,
                "value": {
                    "path": str(dest_file),
                    "width": w,
                    "height": h,
                    "skipped": False,
                },
                "error": None,
            }
        except Exception as exc:
            logging.warning("export_preview failure: %s", exc)
            from previewgen.errors import classify_exception
            code, msg = classify_exception(exc)
            return {"ok": False, "value": None, "error": msg, "code": code}
        finally:
            if temp_dir and temp_dir.exists():
                safe_rmtree(temp_dir, "on-demand export temp")

    def start_batch(self, input_folder: str, output_folder: str, config_dict: dict[str, Any]) -> None:
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
        self.preview_coordinator.shutdown()
        self.probe_coordinator.shutdown()
        self.lifecycle.cleanup()

# Note: Desktop shortcut management is the responsibility of system installers
# Runtime auto-shortcut creation removed per security and packaging best practices.
