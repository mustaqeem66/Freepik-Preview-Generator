"""
PreviewGen Live Preview Isolation and Coordination

Executes interactive live preview rendering in an isolated, supervised child
process with latest-wins queue semantics and process tree termination on timeout
or cancellation.

Prevents GUI thread hangs:
- Returns an operationId immediately to pywebview.
- Dispatches preview.completed or preview.failed via the typed event envelope.
- Drops superseded/stale queued requests instantly.
- Signals termination to active child workers when a newer request arrives.
"""
from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import os
import queue as queue_module
import sys
import tempfile
import threading
import time
import urllib.parse
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from previewgen import config as previewgen_config
from previewgen import proc
from previewgen.tempfiles import safe_rmtree

if TYPE_CHECKING:
    from previewgen.preview_server import PreviewFileServer

DEFAULT_PREVIEW_TIMEOUT_SECONDS = 10.0
_KILL_TIMEOUT_SECONDS = 3.0


def _preview_worker(
    source_spec: str,
    config_dict: dict[str, Any],
    max_dimension: int,
    result_queue: Any,
) -> None:  # pragma: no cover - runs in child process
    """Child worker process that extracts archives, decodes, composes, and encodes the preview JPEG."""
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.setsid()

    proc.apply_memory_limit(previewgen_config.MAX_RENDERER_MEMORY_BYTES)
    extracted_temp: Path | None = None

    try:
        from previewgen.config import PreviewConfig
        from previewgen.renderers.pipeline import preview_jpeg_bytes

        if source_spec.startswith("zip://"):
            import urllib.parse
            import zipfile

            from previewgen import limits

            parsed = urllib.parse.urlparse(source_spec)
            zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
            entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
            if not zip_path.is_file() or not entry_name:
                raise ValueError("Invalid zip entry URI")

            extracted_temp = Path(tempfile.mkdtemp(prefix="previewgen_worker_zip_"))
            target_file = extracted_temp / Path(entry_name).name
            with zipfile.ZipFile(zip_path, "r") as zf:
                limits.extract_zip_member_bounded(zf, entry_name, target_file)
            source_path = target_file
        else:
            source_path = Path(source_spec)

        cfg = PreviewConfig.from_mapping(config_dict, mode="preview")
        cfg.position = "custom"

        jpeg_bytes, orig_w, orig_h = preview_jpeg_bytes(source_path, cfg, max_dimension=max_dimension)
        result_queue.put({
            "status": "success",
            "jpeg_bytes": jpeg_bytes,
            "width": orig_w,
            "height": orig_h,
        })
    except Exception as exc:
        with contextlib.suppress(Exception):
            result_queue.put({
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
            })
    finally:
        if extracted_temp and extracted_temp.exists():
            safe_rmtree(extracted_temp, "child worker zip temp")

def _materialize_source(source: str | Path) -> tuple[Path, Path | None]:
    """Resolve a plain path or ``zip://`` URI to a concrete file to render.

    This runs on the coordinator worker thread (never the pywebview bridge
    thread), so extracting a large archive member cannot stall the GUI. Returns
    the resolved source path and, when an extraction occurred, the temp root the
    caller must remove.
    """
    text = str(source)
    if not text.startswith("zip://"):
        return Path(text).resolve(), None

    from previewgen import limits

    parsed = urllib.parse.urlparse(text)
    zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
    entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
    if not zip_path.is_file() or not entry_name:
        raise ValueError("Invalid zip entry URI")

    temp_root = Path(tempfile.mkdtemp(prefix="previewgen_ondemand_"))
    target = temp_root / Path(entry_name).name
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            limits.extract_zip_member_bounded(zf, entry_name, target)
    except Exception:
        safe_rmtree(temp_root, "failed on-demand preview extraction")
        raise
    return target, temp_root


class PreviewCoordinator:
    """
    Supervises live preview requests with latest-wins semantics.
    Ensures at most one active preview process and one pending latest request.
    """

    def __init__(self, preview_server: PreviewFileServer) -> None:
        self.preview_server = preview_server
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._active_process: mp.Process | None = None
        self._active_job: Any | None = None
        self._active_op_id: str | None = None
        self._pending_task: dict[str, Any] | None = None
        self._cancel_requested = False
        self._dispatch_fn: Callable[[str, dict[str, Any], str], None] | None = None
        self._running = True

    def set_dispatch_fn(self, dispatch_fn: Callable[[str, dict[str, Any], str], None]) -> None:
        self._dispatch_fn = dispatch_fn

    def submit_preview(
        self,
        operation_id: str,
        source: str | Path,
        config_dict: dict[str, Any],
        max_dimension: int = 850,
    ) -> None:
        """Submit a preview request. Cancels any stale active render and queues newest.

        ``source`` may be a filesystem path or a ``zip://`` URI; archive members
        are extracted on the worker thread, never on the pywebview bridge thread.

        This is a control-plane call: it only records the newest request and
        returns. The supervisor thread observes the new pending request and reaps
        any running worker off-thread, so this never blocks the bridge.
        """
        with self._lock:
            # Latest-wins: replace the single pending slot. There is never more
            # than one active and one pending request, so no unbounded backlog.
            self._pending_task = {
                "operation_id": operation_id,
                "source": source,
                "config_dict": config_dict,
                "max_dimension": max_dimension,
            }

            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
                self._worker_thread.start()

    def cancel_active(self, operation_id: str | None = None) -> None:
        """Cancel the running and pending preview without blocking the caller."""
        with self._lock:
            if operation_id is None or (
                self._pending_task and self._pending_task.get("operation_id") == operation_id
            ):
                self._pending_task = None

            if operation_id is None or self._active_op_id == operation_id:
                # Signal the supervisor thread to reap the active worker; do not
                # terminate here or a Cancel request would block the bridge until
                # the render process is gone.
                self._cancel_requested = True

    def _take_active_worker(self) -> tuple[mp.Process | None, Any | None]:
        with self._lock:
            proc_ref = self._active_process
            job_ref = self._active_job
            self._active_process = None
            self._active_job = None
        return proc_ref, job_ref

    def _terminate_active_worker(self) -> None:
        """Reap the active worker process tree. Never call while holding the lock."""
        proc_ref, job_ref = self._take_active_worker()
        proc.reap_process_tree(proc_ref, job_ref, kill_timeout=_KILL_TIMEOUT_SECONDS)

    def _run_loop(self) -> None:
        while self._running:
            with self._lock:
                task = self._pending_task
                self._pending_task = None
                if not task:
                    self._active_op_id = None
                    break
                # A freshly dequeued task supersedes any earlier cancel signal.
                self._cancel_requested = False
                self._active_op_id = task["operation_id"]

            op_id = task["operation_id"]
            source = task["source"]
            config_dict = task["config_dict"]
            max_dimension = task["max_dimension"]
            temp_root: Path | None = None

            try:
                res = self._render_isolated(op_id, source, config_dict, max_dimension)
                # Check if this task was superseded while running
                with self._lock:
                    superseded = (
                        self._pending_task is not None
                        or self._active_op_id != op_id
                        or self._cancel_requested
                    )
                if superseded:
                    continue  # Superseded/cancelled, do not publish or dispatch

                if res.get("status") == "success":
                    jpeg_bytes = res["jpeg_bytes"]
                    orig_w = res["width"]
                    orig_h = res["height"]
                    preview_url = self.preview_server.publish_jpeg(jpeg_bytes)
                    preview_id = preview_url.split("/")[-1] if "/" in preview_url else preview_url
                    if self._dispatch_fn:
                        self._dispatch_fn(
                            "preview.completed",
                            {
                                "operationId": op_id,
                                "url": preview_url,
                                "previewId": preview_id,
                                "width": orig_w,
                                "height": orig_h,
                            },
                            op_id,
                        )
                else:
                    if self._dispatch_fn:
                        self._dispatch_fn(
                            "preview.failed",
                            {
                                "operationId": op_id,
                                "error": res.get("error", "Preview generation failed"),
                                "code": res.get("error_type", "UNKNOWN"),
                            },
                            op_id,
                        )
            except Exception as exc:
                logging.debug("Preview execution notice for %s: %s", op_id, exc)
                if self._dispatch_fn:
                    self._dispatch_fn(
                        "preview.failed",
                        {
                            "operationId": op_id,
                            "error": str(exc),
                            "code": type(exc).__name__,
                        },
                        op_id,
                    )
            finally:
                if temp_root is not None and temp_root.exists():
                    safe_rmtree(temp_root, "on-demand preview temp")

    def _render_isolated(
        self,
        op_id: str,
        source: str | Path,
        config_dict: dict[str, Any],
        max_dimension: int,
    ) -> dict[str, Any]:
        result_queue: Any = mp.Queue()
        p = mp.Process(
            target=_preview_worker,
            args=(str(source), config_dict, max_dimension, result_queue),
            daemon=True,
        )
        p.start()
        job_ref: Any = None
        if sys.platform == "win32" and p.pid is not None:
            job_ref = proc.WindowsJob(previewgen_config.MAX_RENDERER_MEMORY_BYTES)
            if job_ref.active:
                job_ref.assign(p.pid)
        with self._lock:
            self._active_process = p
            self._active_job = job_ref

        start_t = time.time()
        timeout = DEFAULT_PREVIEW_TIMEOUT_SECONDS
        while p.is_alive():
            with self._lock:
                superseded = (
                    self._active_op_id != op_id
                    or self._pending_task is not None
                    or self._cancel_requested
                )
            if superseded:
                # Cancelled or superseded: reap off-thread (never under the lock).
                self._terminate_active_worker()
                return {"status": "error", "error": "superseded", "error_type": "CANCELLED"}

            if (time.time() - start_t) > timeout:
                src_name = Path(str(source)).name
                logging.warning("Live preview timeout for %s after %.1fs", src_name, timeout)
                self._terminate_active_worker()
                return {"status": "error", "error": f"Preview timed out ({timeout}s)", "error_type": "TIMEOUT"}
            time.sleep(0.04)

        try:
            res = result_queue.get(timeout=1.0)
            return res
        except queue_module.Empty:
            exit_code = p.exitcode
            return {
                "status": "error",
                "error": f"Worker exited with code {exit_code}",
                "error_type": "PROCESS_EXIT",
            }
        finally:
            with contextlib.suppress(Exception):
                result_queue.close()
                result_queue.join_thread()

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
            self._pending_task = None
            self._cancel_requested = True
        self._terminate_active_worker()
        worker = self._worker_thread
        if worker is not None and worker.is_alive():
            with contextlib.suppress(Exception):
                worker.join(timeout=_KILL_TIMEOUT_SECONDS + 1.0)
