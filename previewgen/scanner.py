"""
PreviewGen Scanner Module
GUI-independent folder scanning with cancellation and bounded traversal.
"""
from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
import urllib.parse
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from previewgen import limits
from previewgen.config import (
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
)
from previewgen.tempfiles import create_temp_dir, safe_rmtree

# Bounds for the interactive folder scan. Module-level so they can be tuned or
# overridden in tests, and so a capped scan can be reported as truncated.
MAX_SCAN_ITEMS = 5000
MAX_SCAN_SECONDS = 20.0
MAX_SCAN_DEPTH = 15


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
    _serializable = False  # never reachable from window.pywebview.api


    def __init__(self) -> None:
        self.active_scan_context: ScanContext | None = None
        self.active_scan_thread: threading.Thread | None = None
        self.scan_lock = threading.Lock()
        self.session_zip_dir: Path | None = None
        self._progress_callback: Callable[[str, int], None] | None = None
        self._finished_callback: Callable[[str, dict[str, Any]], None] | None = None

    def set_callbacks(
        self,
        progress_callback: Callable[[str, int], None] | None = None,
        finished_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Set progress and finished callbacks (used by DesktopApi for JS dispatch)."""
        self._progress_callback = progress_callback
        self._finished_callback = finished_callback

    def cancel_scan(self, scan_id: str | None = None) -> bool:
        """Only cancel the identified scan, never a newer active scan.

        Older internal callers without an ID remain supported. The React
        bridge must send the stable scan ID to avoid delayed-cancel races.
        """
        with self.scan_lock:
            ctx = self.active_scan_context
            if ctx is None or (scan_id is not None and ctx.scan_id != scan_id):
                return False
            ctx.cancel_event.set()
            logging.info("Cancel signal dispatched to scan %s", ctx.scan_id)
            return True

    def start_scan(self, folder_path: str) -> dict[str, Any]:
        """Start background asynchronous folder scan with independent context and cancellation token."""
        with self.scan_lock:
            # Signal any existing active scan to stop (its private cancel_event stays set)
            if self.active_scan_context:
                self.active_scan_context.cancel_event.set()

            # Allocate fresh, completely isolated context for the new scan
            scan_id = uuid.uuid4().hex[:8]
            scan_cancel_event = threading.Event()
            p = Path(folder_path).resolve()
            temp_root = create_temp_dir(prefix=f"previewgen_scan_{scan_id}_")

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
            except Exception as exc:
                logging.warning("Scan %s failed: %s", scan_ctx.scan_id, exc)
                from previewgen.errors import classify_exception
                code, message = classify_exception(exc)
                res = {
                    "files": [], "total": 0, "status": "failed",
                    "error": message, "code": code,
                    "truncated": False, "truncationReasons": [], "discovered": 0,
                }

            # Determine whether this scan is still the active one. A superseded
            # scan must not emit a terminal event that could clobber newer state.
            with self.scan_lock:
                is_current = bool(
                    self.active_scan_context
                    and self.active_scan_context.scan_id == scan_ctx.scan_id
                )

            if is_current and self._finished_callback:
                if scan_ctx.cancel_event.is_set():
                    # Deterministic terminal contract for cancelled scans.
                    payload: dict[str, Any] = {
                        "scanId": scan_ctx.scan_id,
                        "status": "cancelled",
                        "files": [],
                        "total": 0,
                    }
                elif res.get("truncated"):
                    payload = {"scanId": scan_ctx.scan_id, "status": "truncated", **res}
                else:
                    payload = {"scanId": scan_ctx.scan_id, "status": "completed", **res}
                try:
                    self._finished_callback(scan_ctx.scan_id, payload)
                except Exception as exc:
                    logging.debug("Scan finished event dispatch notice: %s", exc)

            # Clean up this scan's private temp directory (log on failure)
            safe_rmtree(scan_ctx.temp_root, "scan temp")

        scan_thread = threading.Thread(target=_scan_worker, args=(ctx,), daemon=True)
        with self.scan_lock:
            self.active_scan_thread = scan_thread
        scan_thread.start()

        return {"ok": True, "scanId": scan_id}

    def scan_folder(self, folder_path: str) -> dict[str, Any]:
        """Synchronous wrapper for folder scanning with strict bounds and isolated context."""
        scan_id = uuid.uuid4().hex[:8]
        temp_root = create_temp_dir(prefix=f"previewgen_sync_scan_{scan_id}_")
        ctx = ScanContext(
            scan_id=scan_id,
            root=Path(folder_path).resolve(),
            cancel_event=threading.Event(),
            temp_root=temp_root,
        )
        try:
            return self._execute_scan(ctx)
        finally:
            safe_rmtree(temp_root, "sync scan temp")

    def _execute_scan(self, ctx: ScanContext) -> dict[str, Any]:
        """Internal scan engine bounded by directory count, file count, and timeouts."""
        p = ctx.root
        if not p.is_dir():
            raise FileNotFoundError("Input folder does not exist")

        files_payload: list[dict[str, Any]] = []
        reasons: list[str] = []

        inaccessible_dirs: list[str] = []

        def _on_error(err: OSError) -> None:
            fn = getattr(err, "filename", None)
            if fn:
                try:
                    rel = str(Path(fn).relative_to(p))
                except Exception:
                    rel = Path(fn).name
            else:
                rel = "?"
            if rel not in inaccessible_dirs:
                inaccessible_dirs.append(rel)
            _mark("permission_denied")
            logging.warning("Folder scan permission denied at %s: %s", rel, err)

        def _mark(reason: str) -> None:
            if reason not in reasons:
                reasons.append(reason)
                logging.warning("Folder scan %s truncated: %s", ctx.scan_id, reason)

        start_time = time.monotonic()
        item_count = 0
        root_real = p.resolve()

        def _grant_of(candidate: Path) -> Path | None:
            """Return the candidate's real path, or None if it leaves the grant.

            ``is_symlink()`` and ``followlinks=False`` only cover POSIX links.
            A Windows junction or mounted folder reports as an ordinary
            directory, so containment has to be decided on the resolved path.
            Resolving once per entry also keeps the cost down: the walk calls
            this for every directory and every file it considers.
            """
            try:
                resolved = candidate.resolve()
            except OSError:
                return None
            if resolved != root_real and root_real not in resolved.parents:
                return None
            return resolved

        try:
            for root, dirs, files in os.walk(p, topdown=True, followlinks=False, onerror=_on_error):
                if ctx.cancel_event.is_set():
                    break
                if (time.monotonic() - start_time) > MAX_SCAN_SECONDS:
                    _mark("maximum_time")
                    break
                rel_root = Path(root).relative_to(p)
                at_depth_cap = len(rel_root.parts) >= MAX_SCAN_DEPTH
                pruned_depth = 0
                kept_dirs: list[str] = []
                for d in dirs:
                    if d.startswith(".") or d == "__MACOSX" or _grant_of(Path(root) / d) is None:
                        continue
                    if at_depth_cap:
                        pruned_depth += 1
                        continue
                    kept_dirs.append(d)
                if pruned_depth:
                    _mark("maximum_depth")
                dirs[:] = kept_dirs
                for f_name in sorted(files):
                    if ctx.cancel_event.is_set():
                        break
                    if (time.monotonic() - start_time) > MAX_SCAN_SECONDS:
                        _mark("maximum_time")
                        return {
                            "files": files_payload, "total": len(files_payload), "truncated": True,
                            "truncationReasons": reasons, "discovered": len(files_payload),
                        }
                    if f_name.startswith(".") or f_name == "Thumbs.db" or f_name.startswith("previewgen_report"):
                        continue
                    item_count += 1
                    if item_count > MAX_SCAN_ITEMS:
                        logging.warning("Folder scan item cap (%d) reached at %s", MAX_SCAN_ITEMS, root)
                        _mark("maximum_files")
                        break
                    f_path = Path(root) / f_name
                    real_path = _grant_of(f_path)
                    if real_path is None or not f_path.is_file():
                        continue
                    ext = f_path.suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS and ext != ".zip":
                        ext_clean = ext.upper().lstrip(".")
                        is_3d = (
                            ext in SUPPORTED_3D_EXTENSIONS and ext != ".blend"
                        ) or ext in (".step", ".stp", ".iges", ".igs")
                        files_payload.append({
                            "name": f_path.name,
                            "path": str(real_path),
                            "ext": ext_clean,
                            "is_3d": is_3d,
                        })
                    elif ext == ".zip":
                        try:
                            import zipfile

                            declared_members = limits.zip_declared_member_count(f_path)
                            if (declared_members is not None
                                    and declared_members > limits.MAX_ZIP_DIRECTORY_ENTRIES):
                                _mark("maximum_archive_members")
                                logging.warning(
                                    "Skipping archive %s with %d declared entries (central directory cap)",
                                    f_path.name, declared_members,
                                )
                                continue
                            with zipfile.ZipFile(f_path, "r") as zf:
                                all_members = zf.infolist()
                                members = all_members[:1000]
                                if len(all_members) > len(members):
                                    _mark("maximum_archive_members")
                                for member in members:
                                    if ctx.cancel_event.is_set():
                                        break
                                    if member.is_dir() or member.file_size > 250 * 1024 * 1024:
                                        continue
                                    member_path = Path(member.filename)
                                    clean_name = member_path.name
                                    if clean_name.startswith(".") or any(
                                        part == "__MACOSX" for part in member_path.parts
                                    ):
                                        continue
                                    m_ext = member_path.suffix.lower()
                                    if m_ext in SUPPORTED_EXTENSIONS and m_ext != ".zip":
                                        m_clean = m_ext.upper().lstrip(".")
                                        m_3d = (
                                            m_ext in SUPPORTED_3D_EXTENSIONS and m_ext != ".blend"
                                        ) or m_ext in (".step", ".stp", ".iges", ".igs")
                                        files_payload.append({
                                            "name": f"{f_path.stem}/{clean_name}",
                                            "path": (
                                                f"zip://{urllib.parse.quote(f_path.resolve().as_posix(), safe='/:')}"
                                                f"?{urllib.parse.urlencode({'entry': member.filename})}"
                                            ),
                                            "ext": m_clean,
                                            "is_3d": m_3d,
                                        })
                                        item_count += 1
                                        if item_count > MAX_SCAN_ITEMS:
                                            _mark("maximum_files")
                                            break
                        except Exception as exc:
                            logging.warning("Could not index archive %s: %s", f_path.name, exc)

                # Notify progress every 100 items
                if self._progress_callback and item_count % 100 == 0:
                    with contextlib.suppress(Exception):
                        self._progress_callback(ctx.scan_id, len(files_payload))

                if item_count > MAX_SCAN_ITEMS:
                    break
        except Exception as exc:
            logging.warning("Folder scan interrupted: %s", exc)

        if ctx.cancel_event.is_set():
            final_status = "cancelled"
        elif reasons or inaccessible_dirs:
            final_status = "completed_with_warnings"
        else:
            final_status = "completed"

        return {
            "files": files_payload,
            "total": len(files_payload),
            "status": final_status,
            "truncated": bool(reasons or inaccessible_dirs),
            "truncationReasons": reasons,
            "permissionErrors": len(inaccessible_dirs),
            "inaccessibleDirectories": inaccessible_dirs[:20],
            "remediation": (
                "Check read permissions on the inaccessible directories listed above."
                if inaccessible_dirs
                else None
            ),
            "discovered": len(files_payload),
        }


# Global scanner instance
_scanner_instance: ScannerService | None = None


def get_scanner() -> ScannerService:
    """Get or create the global scanner service instance."""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = ScannerService()
    return _scanner_instance
