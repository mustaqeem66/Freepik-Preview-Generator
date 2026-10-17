"""
PreviewGen Scanner Module
GUI-independent folder scanning with cancellation and bounded traversal.
"""
from __future__ import annotations
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from processor import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_CAD_EXTENSIONS,
)


@dataclass
class ScanContext:
    """Isolated scan context with independent cancellation and temp directory."""
    scan_id: str
    root: Path
    cancel_event: threading.Event
    temp_root: Path


class ScannerService:
    """
    Background folder scanning service with cancellation, quotas, and progress events.
    Completely GUI-independent - no webview imports.
    """
    
    def __init__(self) -> None:
        self.active_scan_context: Optional[ScanContext] = None
        self.active_scan_thread: Optional[threading.Thread] = None
        self.scan_lock = threading.Lock()
        self.session_zip_dir: Optional[Path] = None
        self._progress_callback: Optional[Callable[[str, int], None]] = None
        self._finished_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def set_callbacks(
        self,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        finished_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        """Set progress and finished callbacks (used by DesktopApi for JS dispatch)."""
        self._progress_callback = progress_callback
        self._finished_callback = finished_callback

    def cancel_scan(self) -> None:
        """Signal active folder scan to stop."""
        with self.scan_lock:
            if self.active_scan_context:
                self.active_scan_context.cancel_event.set()
                logging.info("Cancel signal dispatched to scan %s", self.active_scan_context.scan_id)

    def start_scan(self, folder_path: str) -> Dict[str, Any]:
        """Start background asynchronous folder scan with independent context and cancellation token."""
        with self.scan_lock:
            # Signal any existing active scan to stop (its private cancel_event stays set)
            if self.active_scan_context:
                self.active_scan_context.cancel_event.set()

            # Allocate fresh, completely isolated context for the new scan
            scan_id = uuid.uuid4().hex[:8]
            scan_cancel_event = threading.Event()
            p = Path(folder_path).resolve()
            temp_root = Path(tempfile.mkdtemp(prefix=f"previewgen_scan_{scan_id}_"))

            ctx = ScanContext(
                scan_id=scan_id,
                root=p,
                cancel_event=scan_cancel_event,
                temp_root=temp_root,
            )
            self.active_scan_context = ctx

        def _scan_worker(scan_ctx: ScanContext) -> None:
            try:
                res = self._execute_scan(scan_ctx)
                # Only notify if this scan was NOT cancelled and is still the active scan
                if not scan_ctx.cancel_event.is_set():
                    with self.scan_lock:
                        is_current = (
                            self.active_scan_context
                            and self.active_scan_context.scan_id == scan_ctx.scan_id
                        )
                    if is_current and self._finished_callback:
                        try:
                            self._finished_callback(scan_ctx.scan_id, res)
                        except Exception as exc:
                            logging.debug("Scan finished event dispatch notice: %s", exc)
            finally:
                # Clean up this scan's private temp directory
                if scan_ctx.temp_root.exists():
                    shutil.rmtree(scan_ctx.temp_root, ignore_errors=True)

        scan_thread = threading.Thread(target=_scan_worker, args=(ctx,), daemon=True)
        with self.scan_lock:
            self.active_scan_thread = scan_thread
        scan_thread.start()

        return {"ok": True, "scanId": scan_id}

    def scan_folder(self, folder_path: str) -> Dict[str, Any]:
        """Synchronous wrapper for folder scanning with strict bounds and isolated context."""
        scan_id = uuid.uuid4().hex[:8]
        temp_root = Path(tempfile.mkdtemp(prefix=f"previewgen_sync_scan_{scan_id}_"))
        ctx = ScanContext(
            scan_id=scan_id,
            root=Path(folder_path).resolve(),
            cancel_event=threading.Event(),
            temp_root=temp_root,
        )
        try:
            return self._execute_scan(ctx)
        finally:
            if temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)

    def _execute_scan(self, ctx: ScanContext) -> Dict[str, Any]:
        """Internal scan engine bounded by directory count, file count, and timeouts."""
        p = ctx.root
        if not p.is_dir():
            return {"files": [], "total": 0}

        files_payload: List[Dict[str, Any]] = []
        MAX_SCANNED_ITEMS = 5000
        MAX_SCAN_SECONDS = 20.0
        start_time = time.time()
        item_count = 0

        try:
            for root, dirs, files in os.walk(p, topdown=True, followlinks=False):
                if ctx.cancel_event.is_set() or (time.time() - start_time) > MAX_SCAN_SECONDS:
                    logging.info("Folder scan %s stopped: cancelled or time limit exceeded.", ctx.scan_id)
                    break
                rel_root = Path(root).relative_to(p)
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d != "__MACOSX" and len(rel_root.parts) < 15
                ]
                for f_name in sorted(files):
                    if ctx.cancel_event.is_set():
                        break
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
                        try:
                            import zipfile
                            with zipfile.ZipFile(f_path, "r") as zf:
                                members = zf.infolist()[:1000]
                                for member in members:
                                    if ctx.cancel_event.is_set():
                                        break
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

                # Notify progress every 100 items
                if self._progress_callback and item_count % 100 == 0:
                    try:
                        self._progress_callback(ctx.scan_id, len(files_payload))
                    except Exception:
                        pass

                if item_count > MAX_SCANNED_ITEMS:
                    break
        except Exception as exc:
            logging.warning("Folder scan interrupted: %s", exc)

        return {"files": files_payload, "total": len(files_payload)}


# Global scanner instance
_scanner_instance: Optional[ScannerService] = None


def get_scanner() -> ScannerService:
    """Get or create the global scanner service instance."""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = ScannerService()
    return _scanner_instance