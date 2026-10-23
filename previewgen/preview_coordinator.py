"""
PreviewGen Live Preview Isolation and Coordination

Executes interactive live preview rendering in a single long-lived, supervised
child process ("worker slot") with latest-wins queue semantics and process tree
termination on timeout or cancellation.

Prevents GUI thread hangs:
- Returns an operationId immediately to pywebview (control plane).
- Dispatches preview.completed or preview.failed via the typed event envelope.
- Drops superseded/stale queued requests instantly.
- Keeps one warm worker between jobs so interactive changes do not pay
  process-startup cost on every request; the worker is reaped only on crash,
  timeout, supersede/cancel while busy, or shutdown.

Queue policy: at most one active job and one pending request; the newest request
replaces the pending one. There is never an unbounded backlog.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from previewgen import config as previewgen_config
from previewgen.tempfiles import safe_rmtree
from previewgen.worker_slot import WorkerSlot

if TYPE_CHECKING:
    from previewgen.preview_server import PreviewFileServer

DEFAULT_PREVIEW_TIMEOUT_SECONDS = 10.0
_KILL_TIMEOUT_SECONDS = 3.0


def _preview_worker(job_queue: Any, result_queue: Any) -> None:  # pragma: no cover - child process
    """Long-lived child worker: extract archives, decode, compose, encode JPEG.

    Consumes ``(job_id, payload)`` tuples until it is killed or sent ``None``.
    The process stays warm between jobs; the parent reaps it when a job is
    superseded, times out, or crashes.
    """
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.setsid()

    proc_limit = previewgen_config.MAX_RENDERER_MEMORY_BYTES
    from previewgen import proc as proc_module

    proc_module.apply_memory_limit(proc_limit)

    from previewgen.config import PreviewConfig
    from previewgen.renderers.pipeline import preview_jpeg_bytes, source_preview_jpeg_bytes

    while True:
        job = job_queue.get()
        if job is None:
            return
        job_id, payload = job
        extracted_temp: Path | None = None
        try:
            from previewgen import limits

            source_spec = str(payload["source"])
            if source_spec.startswith("zip://"):
                parsed = urllib.parse.urlparse(source_spec)
                zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                if not zip_path.is_file() or not entry_name:
                    raise ValueError("Invalid zip entry URI")

                extracted_temp = Path(tempfile.mkdtemp(prefix="previewgen_worker_zip_"))
                target_file = extracted_temp / Path(entry_name).name
                with limits.open_zip_bounded(zip_path) as zf:
                    limits.extract_zip_member_bounded(zf, entry_name, target_file)
                source_path = target_file
            else:
                source_path = Path(source_spec)

            cfg = PreviewConfig.from_mapping(payload["config_dict"], mode="preview")
            cfg.position = "custom"

            if payload.get("source_only") is True:
                jpeg_bytes, orig_w, orig_h = source_preview_jpeg_bytes(
                    source_path, max_dimension=payload["max_dimension"]
                )
            else:
                jpeg_bytes, orig_w, orig_h = preview_jpeg_bytes(
                    source_path, cfg, max_dimension=payload["max_dimension"]
                )
            result_queue.put({
                "job_id": job_id,
                "status": "success",
                "jpeg_bytes": jpeg_bytes,
                "width": orig_w,
                "height": orig_h,
            })
        except Exception as exc:
            with contextlib.suppress(Exception):
                result_queue.put({
                    "job_id": job_id,
                    "status": "error",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                })
        finally:
            if extracted_temp and extracted_temp.exists():
                safe_rmtree(extracted_temp, "child worker zip temp")


def _materialize_source(source: str | Path) -> tuple[Path, Path | None]:
    """Resolve a plain path or ``zip://`` URI to a concrete file to render.

    Returns the resolved source path and, when an extraction occurred, the temp
    root the caller must remove. (The live worker performs its own extraction;
    this helper is retained for direct callers/tests.)
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
        with limits.open_zip_bounded(zip_path) as zf:
            limits.extract_zip_member_bounded(zf, entry_name, target)
    except Exception:
        safe_rmtree(temp_root, "failed on-demand preview extraction")
        raise
    return target, temp_root


class PreviewCoordinator:
    """
    Supervises live preview requests with latest-wins semantics.
    Ensures at most one active preview job and one pending latest request.
    """
    _serializable = False  # never reachable from window.pywebview.api


    def __init__(self, preview_server: PreviewFileServer) -> None:
        self.preview_server = preview_server
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._slot = WorkerSlot(
            _preview_worker,
            name="preview",
            memory_limit_bytes=previewgen_config.MAX_RENDERER_MEMORY_BYTES,
            kill_timeout=_KILL_TIMEOUT_SECONDS,
        )
        self._sync_slot = WorkerSlot(
            _preview_worker,
            name="preview_sync",
            memory_limit_bytes=previewgen_config.MAX_RENDERER_MEMORY_BYTES,
            kill_timeout=_KILL_TIMEOUT_SECONDS,
        )
        self._sync_lock = threading.Lock()
        self._sync_busy = False
        self._active_op_id: str | None = None
        self._pending_task: dict[str, Any] | None = None
        self._cancel_requested = False
        self._dispatch_fn: Callable[[str, dict[str, Any], str], None] | None = None
        self._running = True

    def set_dispatch_fn(self, dispatch_fn: Callable[[str, dict[str, Any], str], None]) -> None:
        self._dispatch_fn = dispatch_fn

    def is_busy(self) -> bool:
        """True while a preview is queued, rendering, or a sync render holds the slot.

        Used by the desktop watchdog to distinguish a genuinely frozen bridge
        from an idle app where the user simply is not interacting.
        """
        with self._lock:
            active = self._active_op_id is not None or self._pending_task is not None
        return active or self._sync_busy

    def submit_preview(
        self,
        operation_id: str,
        source: str | Path,
        config_dict: dict[str, Any],
        max_dimension: int = 850,
    ) -> None:
        """Submit a preview request. Queues the newest and returns immediately.

        ``source`` may be a filesystem path or a ``zip://`` URI; archive members
        are extracted in the child worker, never on the pywebview bridge thread.

        Control-plane call: it only records the newest request and returns. The
        supervisor thread observes the new pending request and reaps any running
        worker off-thread, so this never blocks the bridge.
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

    def _run_loop(self) -> None:
        try:
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

                try:
                    res = self._render_isolated(
                        op_id, task["source"], task["config_dict"], task["max_dimension"]
                    )
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
                        metrics = res.get("metrics", {})
                        logging.info(
                            "Preview generated [op=%s, totalMs=%.1f, renderMs=%.1f]",
                            op_id,
                            metrics.get("totalMs", 0.0),
                            metrics.get("renderMs", 0.0),
                        )
                        if self._dispatch_fn:
                            self._dispatch_fn(
                                "preview.completed",
                                {
                                    "operationId": op_id,
                                    "url": preview_url,
                                    "previewId": preview_id,
                                    "width": orig_w,
                                    "height": orig_h,
                                    "metrics": metrics,
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
            # The loop can only exit while holding no work, but a submit that
            # wins the lock between the exit decision and this thread actually
            # stopping would see is_alive() true and queue work for nobody.
            # Clearing the reference under the lock -- and respawning if a task
            # arrived in that window -- closes it.
            with self._lock:
                if self._worker_thread is threading.current_thread():
                    self._worker_thread = None
                    if self._running and self._pending_task is not None:
                        self._worker_thread = threading.Thread(
                            target=self._run_loop, daemon=True)
                        self._worker_thread.start()

    def _render_isolated(
        self,
        op_id: str,
        source: str | Path,
        config_dict: dict[str, Any],
        max_dimension: int,
    ) -> dict[str, Any]:
        self._slot.ensure_started()
        job_id = self._slot.send({
            "source": str(source),
            "config_dict": config_dict,
            "max_dimension": max_dimension,
        })

        display_name = Path(str(source)).name or str(source)
        start_t = time.monotonic()
        timeout = DEFAULT_PREVIEW_TIMEOUT_SECONDS
        while True:
            with self._lock:
                superseded = (
                    self._active_op_id != op_id
                    or self._pending_task is not None
                    or self._cancel_requested
                )
            if superseded:
                # Cancelled or superseded: reap off-thread (never under the lock).
                self._slot.kill()
                return {"status": "error", "error": "superseded", "error_type": "CANCELLED"}

            if (time.monotonic() - start_t) > timeout:
                logging.warning("Live preview timeout for %s after %.1fs", display_name, timeout)
                self._slot.kill()
                return {"status": "error", "error": f"Preview timed out ({timeout}s)", "error_type": "TIMEOUT"}

            res = self._slot.poll(job_id, timeout=0.04)
            if res is not None:
                total_ms = (time.monotonic() - start_t) * 1000.0
                res["metrics"] = {"totalMs": total_ms, "renderMs": total_ms}
                return res

            if not self._slot.alive():
                exit_code = self._slot.exitcode
                self._slot.kill()
                return {
                    "status": "error",
                    "error": f"Preview worker exited with code {exit_code}",
                    "error_type": "PROCESS_EXIT",
                }

    def render_sync(
        self,
        source: str | Path,
        config_dict: dict[str, Any],
        max_dimension: int = 850,
        timeout_seconds: float = DEFAULT_PREVIEW_TIMEOUT_SECONDS,
        *,
        source_only: bool = False,
    ) -> dict[str, Any]:
        """Bounded synchronous preview render for legacy/CLI callers.

        Runs in a dedicated worker slot (never in-process on the caller's
        thread) with a hard timeout, so a hostile asset cannot pin a caller
        that executes this directly on the pywebview bridge thread. Uses its
        own slot so it can never collide with the live async worker.
        """
        with self._sync_lock:
            self._sync_busy = True
            try:
                self._sync_slot.ensure_started()
                job_id = self._sync_slot.send({
                    "source": str(source),
                    "config_dict": config_dict,
                    "max_dimension": max_dimension,
                    "source_only": source_only,
                })
                start_t = time.monotonic()
                while True:
                    if (time.monotonic() - start_t) > timeout_seconds:
                        logging.warning("Synchronous preview timeout for %s after %.1fs", source, timeout_seconds)
                        self._sync_slot.kill()
                        return {
                            "status": "error",
                            "error": f"Preview timed out ({timeout_seconds}s)",
                            "error_type": "TIMEOUT",
                        }
                    res = self._sync_slot.poll(job_id, timeout=0.05)
                    if res is not None:
                        return res
                    if not self._sync_slot.alive():
                        exit_code = self._sync_slot.exitcode
                        self._sync_slot.kill()
                        return {
                            "status": "error",
                            "error": f"Preview worker exited with code {exit_code}",
                            "error_type": "PROCESS_EXIT",
                        }
            finally:
                self._sync_busy = False

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
            self._pending_task = None
            self._cancel_requested = True
        self._slot.kill()
        with self._sync_lock:
            self._sync_slot.kill()
        worker = self._worker_thread
        if worker is not None and worker.is_alive():
            with contextlib.suppress(Exception):
                worker.join(timeout=_KILL_TIMEOUT_SECONDS + 1.0)
