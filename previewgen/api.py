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
import time
import uuid
from pathlib import Path

# Use TYPE_CHECKING to avoid runtime webview import
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from previewgen import limits
from previewgen.assets import calculate_export_dimensions as _calc_export_dimensions
from previewgen.config import DISCOVERY_MAX_FILES, SUPPORTED_3D_EXTENSIONS, SUPPORTED_EXTENSIONS, PreviewConfig
from previewgen.lifecycle import ActiveOperation, LifecycleManager
from previewgen.preview_coordinator import DEFAULT_PREVIEW_TIMEOUT_SECONDS, PreviewCoordinator
from previewgen.preview_server import PreviewFileServer
from previewgen.probe_coordinator import ProbeCoordinator
from previewgen.probe_process import probe_asset_isolated
from previewgen.renderer_process import render_file_isolated
from previewgen.scanner import get_scanner
from previewgen.settings import load_settings, save_settings
from previewgen.tempfiles import safe_rmtree
from previewgen.thumbnail_coordinator import MAX_VISIBLE_THUMBNAILS, ThumbnailCoordinator


# Large scans used to send all 5000 assets in one evaluate_js call. The
# terminal event is now metadata-only above this threshold; React pulls
# small bounded pages over the existing asynchronous desktop bridge.
SCAN_INLINE_RESULT_LIMIT = 128
SCAN_PAGE_MAX_ITEMS = 128
SCAN_PAGE_MAX_BYTES = 32 * 1024


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
        self.thumbnail_coordinator = ThumbnailCoordinator(
            self.preview_server, self.preview_coordinator.render_sync, self._dispatch_envelope
        )
        # A separate one-item cache ensures source comparison does not evict
        # the active gallery images. Both share the bounded sync worker slot.
        self.comparison_coordinator = ThumbnailCoordinator(
            self.preview_server, self.preview_coordinator.render_sync, self._dispatch_envelope,
            max_visible=1, max_retained=1, max_dimension=850, timeout=10.0,
            event_prefix="comparison", source_only=True,
        )
        self.probe_coordinator = ProbeCoordinator()
        self.probe_coordinator.set_dispatch_fn(self._dispatch_envelope)
        self._preview_request_lock = threading.Lock()
        self._latest_preview_request_id = 0
        self._batch_start_lock = threading.Lock()
        self._batch_operation_id = ""
        self._sequence_counter = itertools.count(1)
        self._authorized_folders: set[Path] = set()
        self._authorized_files: set[Path] = set()
        self._authorized_output_folders: set[Path] = set()
        self._authorized_lock = threading.Lock()
        self._scan_page_lock = threading.Lock()
        self._scan_page_state: tuple[str, list[dict[str, Any]], int] | None = None
        self._scan_paging_enabled = False
        self._last_heartbeat_time = time.time()
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
        with contextlib.suppress(Exception), self._authorized_lock:
            self._authorized_folders.add(Path(folder).resolve())

    def is_authorized_path(self, path: Path | str) -> bool:
        try:
            target = Path(path).resolve()
            with self._authorized_lock:
                roots = tuple(self._authorized_folders)
            for auth in roots:
                try:
                    target.relative_to(auth)
                    return True
                except ValueError:
                    continue
            return False
        except Exception:
            return False

    def add_authorized_output_folder(self, folder: Path | str) -> None:
        """Grant output capability only through the native destination picker."""
        target = Path(folder).resolve()
        self.add_authorized_folder(target)
        with self._authorized_lock:
            self._authorized_output_folders.add(target)

    def is_authorized_output_path(self, path: Path | str) -> bool:
        """Check explicit destination grants, independently of source roots."""
        try:
            target = Path(path).resolve()
            with self._authorized_lock:
                roots = tuple(self._authorized_output_folders)
            return any(target == root or root in target.parents for root in roots)
        except (OSError, ValueError, TypeError):
            return False

    def is_authorized_selected_file(self, path: Path | str) -> bool:
        """File-picker grants are exact source paths, never parent directories."""
        try:
            candidate = Path(path).resolve()
            with self._authorized_lock:
                return candidate in self._authorized_files
        except (OSError, ValueError, TypeError):
            return False

    def has_outstanding_work(self) -> bool:
        """True when asynchronous work is queued or running right now.

        The desktop watchdog needs to tell a frozen bridge apart from an idle
        application: heartbeats only advance when Python pushes an event, so
        without this the watchdog would report a stall every time the user
        simply paused.
        """
        try:
            if self.lifecycle.get_active_operations():
                return True
            if (self.preview_coordinator.is_busy() or self.probe_coordinator.is_busy()
                    or self.thumbnail_coordinator.is_busy()
                    or self.comparison_coordinator.is_busy()):
                return True
            thread = self.scanner.active_scan_thread
            if thread is not None and thread.is_alive():
                return True
            batch = self.lifecycle.batch_thread
            if batch is not None and batch.is_alive():
                return True
        except Exception:
            # Fail safe toward "busy": a broken probe should not spam stack dumps.
            return True
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
        self._last_heartbeat_time = time.time()
        seq = next(self._sequence_counter)
        op_id = operation_id or payload.get("scanId") or f"op_{seq}"
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
        """Keep large scan rows off the synchronous evaluate_js event path."""
        files = result.get("files")
        if (self._scan_paging_enabled and isinstance(files, list) and (
            len(files) > SCAN_INLINE_RESULT_LIMIT
            or len(json.dumps(files, ensure_ascii=False).encode("utf-8")) > SCAN_PAGE_MAX_BYTES
        )):
            # Scanner callbacks can race a newer scan start just after their
            # own is-current check. Never replace the new scan's page cache.
            with self.scanner.scan_lock:
                ctx = self.scanner.active_scan_context
                if ctx is not None and ctx.scan_id != scan_id:
                    return
                with self._scan_page_lock:
                    self._scan_page_state = (scan_id, files, 0)
            metadata = dict(result)
            metadata["files"] = []
            metadata["paged"] = {"total": len(files), "pageSize": SCAN_PAGE_MAX_ITEMS}
        else:
            with self.scanner.scan_lock:
                ctx = self.scanner.active_scan_context
                if ctx is not None and ctx.scan_id != scan_id:
                    return
                with self._scan_page_lock:
                    self._scan_page_state = None
            metadata = result
        self._dispatch_envelope(
            "scan.finished", {"scanId": scan_id, "result": metadata},
            operation_id=scan_id, terminal=True,
        )

    def get_scan_page(self, scan_id: str, offset: int, limit: int = SCAN_PAGE_MAX_ITEMS) -> dict[str, Any]:
        """Return one sequential, byte-limited page of the last completed scan.

        This contains exactly the same source metadata the selected user scan
        would have sent in scan.finished; it does not grant filesystem access.
        Pages are consumed in order, with no second unbounded JS injection.
        """
        if (not isinstance(scan_id, str) or not scan_id
                or isinstance(offset, bool) or not isinstance(offset, int)
                or isinstance(limit, bool) or not isinstance(limit, int)
                or not 1 <= limit <= SCAN_PAGE_MAX_ITEMS or offset < 0):
            return {"ok": False, "value": None, "error": "INVALID_SCAN_PAGE"}
        with self._scan_page_lock:
            stored = self._scan_page_state
            if not stored or scan_id != stored[0]:
                return {"ok": False, "value": None, "error": "SCAN_RESULT_EXPIRED"}
            _, files, expected = stored
            if offset != expected or offset >= len(files):
                return {"ok": False, "value": None, "error": "SCAN_PAGE_OUT_OF_ORDER"}

            chunk: list[dict[str, Any]] = []
            payload_bytes = 512
            for file in files[offset:offset + limit]:
                encoded_size = len(json.dumps(file, ensure_ascii=False).encode("utf-8")) + 2
                if payload_bytes + encoded_size > SCAN_PAGE_MAX_BYTES:
                    if not chunk:
                        return {"ok": False, "value": None, "error": "SCAN_ROW_TOO_LARGE"}
                    break
                chunk.append(file)
                payload_bytes += encoded_size
            next_offset = offset + len(chunk)
            if next_offset >= len(files):
                self._scan_page_state = None
            else:
                self._scan_page_state = (scan_id, files, next_offset)
            return {
                "ok": True, "error": None,
                "value": {
                    "scanId": scan_id, "offset": offset, "total": len(files),
                    "nextOffset": next_offset, "files": chunk,
                },
            }

    def _on_batch_finished(
        self, summary: dict[str, Any], operation_id: str = "", notify_enabled: bool = False
    ) -> None:
        self._dispatch_envelope(
            "batch.finished", self._sanitize_batch_summary(summary),
            operation_id=operation_id or self._batch_operation_id, terminal=True,
        )
        if notify_enabled:
            from previewgen.notifications import notify_batch_finished
            threading.Thread(
                target=notify_batch_finished, args=(self._sanitize_batch_summary(summary),),
                name="previewgen-desktop-notify", daemon=True,
            ).start()

    @staticmethod
    def _sanitize_batch_summary(summary: dict[str, Any]) -> dict[str, Any]:
        """Keep large per-file reports on disk, not inside a JavaScript event."""
        result = {key: value for key, value in summary.items() if key != "files"}
        errors = result.get("errors")
        if isinstance(errors, list):
            result["errorCount"] = len(errors)
            result["errorsTruncated"] = len(errors) > 50
            result["errors"] = errors[:50]
        return result
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
        # Paths restored from this user's on-disk preferences should retain the
        # native folder-picker authorization across desktop restarts. This is
        # a local-user trust decision, not a security boundary against malware
        # that can already edit the settings file on disk.
        for key in ("inputFolder", "outputFolder"):
            selected = validated.get(key)
            if isinstance(selected, str) and selected.strip() and Path(selected).is_dir():
                if key == "outputFolder":
                    self.add_authorized_output_folder(selected)
                else:
                    self.add_authorized_folder(selected)
        return {"ok": True, "value": validated, "error": None}

    def save_settings(self, settings_dict: dict[str, Any]) -> dict[str, Any]:
        """Save user preferences atomically to disk with backup and schema version."""
        if not isinstance(settings_dict, dict):
            return {"ok": False, "value": False, "error": "Invalid settings payload"}
        # The persisted outputFolder is restored by get_initial_state() as an
        # explicit output grant. Forbid a bridge caller from saving a new
        # arbitrary path and then calling get_initial_state() to launder that
        # unselected path into an authorized output directory.
        output_folder = settings_dict.get("outputFolder")
        if (
            isinstance(output_folder, str)
            and output_folder.strip()
            and not self.is_authorized_output_path(output_folder)
        ):
            return {
                "ok": False, "value": False, "error": "UNAUTHORIZED_OUTPUT_PATH",
                "code": "UNAUTHORIZED_OUTPUT_PATH",
            }
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

    def browse_files(self) -> dict[str, Any]:
        """Native multi-file selection; grant exact read capability for each supported file.

        No directory is added to _authorized_folders. Unsupported/missing files
        are reported to the user instead of quietly appearing as exportable.
        """
        if not self.window:
            return {"ok": False, "value": None, "error": "Native file picker is unavailable"}
        try:
            res = self.window.create_file_dialog(
                int(__import__("webview").OPEN_DIALOG), allow_multiple=True,
            )
            if not res:
                return {"ok": True, "value": {"files": [], "rejected": []}, "error": None}
            files: list[dict[str, Any]] = []
            rejected: list[str] = []
            seen: set[Path] = set()
            if len(res) > 5000:
                return {"ok": False, "value": None, "error": "Select at most 5000 files at once"}
            for raw in res:
                if not isinstance(raw, (str, os.PathLike)):
                    rejected.append("Invalid picker result")
                    continue
                target = Path(raw).resolve()
                if target in seen:
                    continue
                seen.add(target)
                if not target.is_file():
                    rejected.append(f"{target.name}: file not found")
                    continue
                extension = target.suffix.lower()
                if extension == ".zip":
                    # Folder scanning exposes ZIP members via zip:// handles.
                    # A raw ZIP is not a previewable asset in the file list.
                    rejected.append(f"{target.name}: choose its folder to browse ZIP members")
                    continue
                if extension not in SUPPORTED_EXTENSIONS:
                    rejected.append(f"{target.name}: unsupported format")
                    continue
                with self._authorized_lock:
                    if target not in self._authorized_files and len(self._authorized_files) >= 5000:
                        rejected.append(f"{target.name}: session selection limit (5000 files) reached")
                        continue
                    self._authorized_files.add(target)
                files.append({
                    "name": target.name, "path": str(target),
                    "ext": extension.lstrip(".").upper(),
                    "is_3d": (
                        extension in SUPPORTED_3D_EXTENSIONS and extension != ".blend"
                    ) or extension in (".step", ".stp", ".iges", ".igs"),
                })
            return {"ok": True, "value": {"files": files, "rejected": rejected}, "error": None}
        except Exception as exc:
            logging.warning("Native multi-file picker failed: %s", exc)
            return {"ok": False, "value": None, "error": "Could not open the native file picker"}

    def clear_selected_files(self) -> dict[str, Any]:
        """Revoke all exact-file picker grants when the user clears the list.

        In-flight batch workers own validated path snapshots and are stopped
        separately via cancellation; clearing grants affects future requests.
        """
        with self._authorized_lock:
            removed = len(self._authorized_files)
            self._authorized_files.clear()
        return {"ok": True, "value": removed, "error": None}

    def browse_input_folder(self) -> str:
        """Open native folder picker for input directory."""
        if not self.window:
            return ""
        try:
            res = self.window.create_file_dialog(int(__import__('webview').FOLDER_DIALOG))
            path = res[0] if res else ""
            if path:
                self.add_authorized_folder(path)
            return path
        except Exception as exc:
            logging.warning("Folder dialog failed: %s", exc)
            return ""

    def browse_output_folder(self) -> str:
        """Open native folder picker for output directory."""
        if not self.window:
            return ""
        try:
            res = self.window.create_file_dialog(int(__import__('webview').FOLDER_DIALOG))
            path = res[0] if res else ""
            if path:
                self.add_authorized_output_folder(path)
            return path
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

    def open_diagnostics_folder(self) -> dict[str, Any]:
        """Show the user's local log directory without uploading any diagnostics."""
        from previewgen.settings import get_log_directory

        try:
            folder = get_log_directory()
            folder.mkdir(parents=True, exist_ok=True)
            self.add_authorized_folder(folder)
            return self.open_folder(str(folder))
        except Exception as exc:
            logging.warning("Could not open diagnostics folder: %s", exc)
            return {"ok": False, "error": str(exc)}

    def scan_folder(self, folder_path: str) -> dict[str, Any]:
        """Synchronous scan (used for initial load)."""
        if folder_path and Path(folder_path).is_dir():
            self.add_authorized_folder(folder_path)
        return self.scanner.scan_folder(folder_path)

    def start_scan(self, folder_path: str, paged: bool = False) -> dict[str, Any]:
        """Start scan; only opt-in frontend builds receive paged results."""
        # An older bundled UI calls start_scan(folder) and must continue
        # receiving the original complete scan.finished file list.
        with self._scan_page_lock:
            self._scan_page_state = None
            self._scan_paging_enabled = paged is True
        if folder_path and Path(folder_path).is_dir():
            self.add_authorized_folder(folder_path)
        return self.scanner.start_scan(folder_path)

    def cancel_scan(self, scan_id: str | None = None) -> dict[str, Any]:
        """Request cancellation of a specific scan to prevent stale commands.

        An omitted scan ID is retained for backwards compatibility, but
        current desktop clients should always supply the returned scanId.
        """
        return {"ok": True, "cancelled": self.scanner.cancel_scan(scan_id)}

    def request_thumbnails(self, sources: list[str]) -> dict[str, Any]:
        """Queue ONLY currently visible, authorized assets; do not render on bridge thread.

        The returned map contains session-cached loopback JPEG URLs. Newly
        generated tiles arrive via thumbnail.ready / thumbnail.failed envelopes.
        Frontend source paths never grant new filesystem capabilities.
        """
        if not isinstance(sources, list) or len(sources) > MAX_VISIBLE_THUMBNAILS:
            return {"ok": False, "value": None, "error": "INVALID_THUMBNAIL_SELECTION"}
        validated: list[str] = []
        try:
            import urllib.parse

            for raw in sources:
                if not isinstance(raw, str) or not raw.strip():
                    return {"ok": False, "value": None, "error": "INVALID_THUMBNAIL_SELECTION"}
                if raw.startswith("zip://"):
                    parsed = urllib.parse.urlparse(raw)
                    archive = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                    entry = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                    if (not entry or Path(entry).suffix.lower() not in SUPPORTED_EXTENSIONS
                            or Path(entry).suffix.lower() == ".zip" or archive.suffix.lower() != ".zip"):
                        return {"ok": False, "value": None, "error": "INVALID_THUMBNAIL_SELECTION"}
                    source = archive
                else:
                    source = Path(raw).resolve()
                    if source.suffix.lower() not in SUPPORTED_EXTENSIONS or source.suffix.lower() == ".zip":
                        return {"ok": False, "value": None, "error": "INVALID_THUMBNAIL_SELECTION"}
                # Avoid up to sixteen synchronous file stats on a potentially
                # offline network share. File existence/decoding is checked by
                # the isolated thumbnail worker, never on the bridge thread.
                if not (self.is_authorized_path(source) or self.is_authorized_selected_file(source)):
                    return {"ok": False, "value": None, "error": "UNAUTHORIZED_THUMBNAIL_SOURCE"}
                validated.append(raw)
            urls = self.thumbnail_coordinator.request(validated)
            return {"ok": True, "value": urls, "error": None}
        except Exception as exc:
            logging.debug("Thumbnail scheduling failed: %s", exc)
            return {"ok": False, "value": None, "error": "THUMBNAIL_REQUEST_FAILED"}

    def request_source_comparison(self, source: str) -> dict[str, Any]:
        """Read-only, session-limited source visualization for the Before view.

        Work is queued in the already isolated rendering worker. No arbitrary
        bridge-supplied filesystem path is accepted without an existing grant.
        """
        if source == "":
            try:
                self.comparison_coordinator.request([])
                return {"ok": True, "value": {}, "error": None}
            except Exception:
                return {"ok": False, "value": None, "error": "COMPARISON_UNAVAILABLE"}
        if not isinstance(source, str) or not source.strip():
            return {"ok": False, "value": None, "error": "INVALID_SOURCE"}
        try:
            import urllib.parse

            if source.startswith("zip://"):
                parsed = urllib.parse.urlparse(source)
                target = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                entry = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                extension = Path(entry).suffix.lower()
                if not entry or target.suffix.lower() != ".zip":
                    return {"ok": False, "value": None, "error": "INVALID_SOURCE"}
            else:
                target = Path(source).resolve()
                extension = target.suffix.lower()
            if (extension not in SUPPORTED_EXTENSIONS
                    or extension == ".zip"
                    or extension in SUPPORTED_3D_EXTENSIONS
                    or extension in {".step", ".stp", ".iges", ".igs"}):
                return {"ok": False, "value": None, "error": "UNSUPPORTED_SOURCE_COMPARISON"}
            if not (self.is_authorized_path(target) or self.is_authorized_selected_file(target)):
                return {"ok": False, "value": None, "error": "UNAUTHORIZED_SOURCE"}
            urls = self.comparison_coordinator.request([source])
            return {"ok": True, "value": urls, "error": None}
        except Exception:
            return {"ok": False, "value": None, "error": "COMPARISON_UNAVAILABLE"}

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
        """Synchronous preview fallback retained strictly for test/CLI compatibility.

        Execution is bounded: decoding/rendering happens in the coordinator's
        dedicated sync worker slot with a hard timeout, never on the caller's
        (potentially the pywebview bridge) thread, so a hostile asset cannot
        pin the GUI. ``zip://`` members are extracted inside the worker.
        """
        op_id = f"render_preview_{request_id or uuid.uuid4().hex[:6]}"
        op = ActiveOperation(operation_id=op_id, kind="preview_render")
        self.lifecycle.register_operation(op)
        try:
            if not isinstance(file_path, str) or not file_path.strip():
                return {"ok": False, "value": None, "error": "Empty file path"}

            if file_path.startswith("zip://"):
                import urllib.parse
                parsed = urllib.parse.urlparse(file_path)
                zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                if not zip_path.is_file() or not entry_name:
                    return {"ok": False, "value": None, "error": "Invalid zip entry URI"}
            else:
                source_path = Path(file_path).resolve()
                if not source_path.is_file():
                    return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            res = self.preview_coordinator.render_sync(
                file_path,
                config_dict,
                max_dimension=850,
                timeout_seconds=DEFAULT_PREVIEW_TIMEOUT_SECONDS,
            )
            if res.get("status") != "success":
                raise RuntimeError(res.get("error") or "Preview generation failed")

            jpeg_bytes = res["jpeg_bytes"]
            preview_url = self.preview_server.publish_jpeg(jpeg_bytes)
            preview_id = preview_url.split("/")[-1] if "/" in preview_url else preview_url
            return {
                "ok": True,
                "value": {
                    "url": preview_url,
                    "previewId": preview_id,
                    "width": res["width"],
                    "height": res["height"],
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
        """Render a single asset to a JPG at the configured export size.

        Rendering runs in an isolated child process with a hard timeout and
        the destination must live under a user-selected (authorized) root.
        """
        temp_dir: Path | None = None
        export_op: ActiveOperation | None = None
        try:
            if not isinstance(file_path, str) or not file_path.strip():
                return {"ok": False, "value": None, "error": "Empty file path"}

            requested_out = config_dict.get("outputFolder") if isinstance(config_dict, dict) else None

            # This runs synchronously on the bridge thread, so it has to be
            # visible to the watchdog; an idle app must not look stalled, but a
            # hung export must.
            export_op = ActiveOperation(operation_id=f"export_{uuid.uuid4().hex[:12]}", kind="single_export")
            self.lifecycle.register_operation(export_op)

            # A zip member's default destination is the archive's folder; the
            # extraction temp dir is deleted in the finally block.
            default_out_dir: Path | None = None

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
                default_out_dir = zip_path.parent
            else:
                source_path = Path(file_path).resolve()
                default_out_dir = source_path.parent

            if not source_path.is_file():
                return {"ok": False, "value": None, "error": f"File does not exist: {source_path.name}"}

            out_dir = Path(
                requested_out if isinstance(requested_out, str) and requested_out.strip() else default_out_dir
            ).resolve()
            if not self.is_authorized_path(out_dir):
                return {"ok": False, "value": None, "error": "UNAUTHORIZED_PATH", "code": "UNAUTHORIZED_PATH"}
            # A file selected directly via Add Files has no authorized
            # writeable parent. Explicit-file exports must use a separate
            # output-folder grant, even if a source-folder scan also happened
            # to authorize the same directory for the legacy workflow.
            if (not file_path.startswith("zip://")
                    and self.is_authorized_selected_file(source_path)
                    and not self.is_authorized_output_path(out_dir)):
                return {"ok": False, "value": None, "error": "UNAUTHORIZED_OUTPUT_PATH",
                        "code": "UNAUTHORIZED_OUTPUT_PATH"}

            cfg = PreviewConfig.from_mapping(config_dict, mode="strict-export")
            out_dir.mkdir(parents=True, exist_ok=True)

            dest_file = out_dir / f"{source_path.stem}.jpg"
            skipped = False
            if dest_file.exists():
                if cfg.overwrite_policy == "skip":
                    skipped = True
                elif cfg.overwrite_policy == "rename":
                    counter = 1
                    while dest_file.exists():
                        dest_file = out_dir / f"{source_path.stem}_copy{counter}.jpg"
                        counter += 1

            if not skipped:
                render_file_isolated(source_path, dest_file, cfg, timeout_seconds=60.0)
            if not dest_file.is_file() or (not skipped and dest_file.stat().st_size == 0):
                return {"ok": False, "value": None, "error": "Export failed"}

            from PIL import Image
            w, h = None, None
            try:
                with Image.open(dest_file) as im:
                    w, h = im.size
            except Exception:
                if not skipped:
                    raise

            return {
                "ok": True,
                "value": {
                    "path": str(dest_file),
                    "width": w,
                    "height": h,
                    "skipped": skipped,
                },
                "error": None,
            }
        except Exception as exc:
            logging.warning("export_preview failure: %s", exc)
            from previewgen.errors import classify_exception
            code, msg = classify_exception(exc)
            return {"ok": False, "value": None, "error": msg, "code": code}
        finally:
            if export_op is not None:
                self.lifecycle.unregister_operation(export_op.operation_id)
            if temp_dir and temp_dir.exists():
                safe_rmtree(temp_dir, "on-demand export temp")

    def start_batch(self, input_folder: str, output_folder: str, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Launch a batch with a stable per-run ID; never block the JS bridge."""
        try:
            cfg = PreviewConfig.from_mapping(config_dict, mode="strict-export")
            cfg.position = "custom"
            source = Path(input_folder).resolve()
            output = Path(output_folder).resolve()
            if not source.is_dir():
                raise ValueError("Input folder does not exist")
            if not output.parent.is_dir():
                raise ValueError("Output folder parent does not exist")
            op_id = f"batch_{uuid.uuid4().hex[:12]}"
            # Never authorize a destination just because JavaScript requested it.
            # Source roots come from the folder chooser or scan workflow; output
            # roots come from the native chooser or restored saved preferences.
            if not self.is_authorized_path(source):
                return {"ok": False, "error": "UNAUTHORIZED_INPUT_PATH"}
            if not self.is_authorized_path(output):
                return {"ok": False, "error": "UNAUTHORIZED_OUTPUT_PATH"}
            with self._batch_start_lock:
                self._batch_operation_id = op_id
                self.lifecycle.start_batch(
                    source, output, cfg,
                    progress_callback=lambda cur, tot, msg: self._dispatch_envelope(
                        "batch.progress", {"current": cur, "total": tot, "message": msg},
                        operation_id=op_id,
                    ),
                    is_cancelled=lambda: False,
                    operation_id=op_id,
                    finished_callback=lambda summary, finished_id: self._on_batch_finished(
                        summary, finished_id, notify_enabled=config_dict.get("desktopNotifications") is True
                    ),
                )
            return {"ok": True, "operationId": op_id}
        except Exception as exc:
            logging.warning("Unable to start batch: %s", exc)
            return {"ok": False, "error": str(exc)}

    def start_batch_files(
        self, file_paths: list[str], output_folder: str, config_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Process only files explicitly granted by the native multi-file picker.

        Input file grants are read-only and exact-match. A separate selected or
        restored output folder remains mandatory; source parents never gain
        implicit write access.
        """
        try:
            if not isinstance(file_paths, list) or not 0 < len(file_paths) <= 5000:
                return {"ok": False, "error": "INVALID_FILE_SELECTION"}
            if not isinstance(output_folder, str) or not output_folder.strip():
                return {"ok": False, "error": "OUTPUT_FOLDER_REQUIRED"}
            output = Path(output_folder).resolve()
            if not self.is_authorized_output_path(output):
                return {"ok": False, "error": "UNAUTHORIZED_OUTPUT_PATH"}
            if not output.parent.is_dir():
                return {"ok": False, "error": "Output folder parent does not exist"}

            selected: list[Path] = []
            seen: set[Path] = set()
            for raw in file_paths:
                if not isinstance(raw, str) or not raw.strip():
                    return {"ok": False, "error": "INVALID_FILE_SELECTION"}
                source = Path(raw).resolve()
                if not self.is_authorized_selected_file(source):
                    return {"ok": False, "error": "UNAUTHORIZED_SELECTED_FILE"}
                if (not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS
                    or source.suffix.lower() == ".zip"):
                    return {"ok": False, "error": f"INVALID_SELECTED_FILE: {source.name}"}
                if source not in seen:
                    seen.add(source)
                    selected.append(source)
            if len(selected) > DISCOVERY_MAX_FILES:
                return {"ok": False, "error": "Selected file limit exceeded"}
            cfg = PreviewConfig.from_mapping(config_dict, mode="strict-export")
            cfg.position = "custom"
            op_id = f"batch_{uuid.uuid4().hex[:12]}"
            with self._batch_start_lock:
                self._batch_operation_id = op_id
                self.lifecycle.start_batch(
                    output, output, cfg,
                    progress_callback=lambda cur, tot, msg: self._dispatch_envelope(
                        "batch.progress", {"current": cur, "total": tot, "message": msg},
                        operation_id=op_id,
                    ),
                    is_cancelled=lambda: False,
                    operation_id=op_id,
                    selected_files=tuple(selected),
                    finished_callback=lambda summary, finished_id: self._on_batch_finished(
                        summary, finished_id, notify_enabled=config_dict.get("desktopNotifications") is True
                    ),
                )
            return {"ok": True, "operationId": op_id}
        except Exception as exc:
            logging.warning("Could not start selected-file batch: %s", exc)
            return {"ok": False, "error": str(exc)}

    def cancel_batch(self) -> dict[str, Any]:
        self.lifecycle.cancel_batch()
        return {"ok": True}

    def cleanup(self) -> None:
        """Orderly shutdown sequence."""
        with self._scan_page_lock:
            self._scan_page_state = None
        self.comparison_coordinator.close()
        self.thumbnail_coordinator.close()
        self.preview_coordinator.shutdown()
        self.probe_coordinator.shutdown()
        self.lifecycle.cleanup()
        self.preview_server.stop()

# Note: Desktop shortcut management is the responsibility of system installers
# Runtime auto-shortcut creation removed per security and packaging best practices.
