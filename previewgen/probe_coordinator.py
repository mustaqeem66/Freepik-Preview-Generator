"""
PreviewGen Asset Probe Isolation and Coordination

Supervises asset metadata probing with asynchronous latest-wins semantics:
- Returns an operationId immediately to pywebview.
- Runs probe inspection inside an isolated, killable child process.
- Dispatches probe.completed or probe.failed via the typed event envelope.
- Drops stale requests and terminates running probe process when selection switches.

Bounds (the queue policy): at most one active probe process and one pending
request; a newer request replaces the pending one and signals the running probe
for cancellation. There is never an unbounded backlog.
"""
from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import os
import queue as queue_module
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from previewgen import config as previewgen_config
from previewgen import proc
from previewgen.tempfiles import safe_rmtree

DEFAULT_PROBE_TIMEOUT_SECONDS = 8.0
_KILL_TIMEOUT_SECONDS = 3.0


def _probe_worker(source_spec: str, result_queue: Any) -> None:  # pragma: no cover
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.setsid()

    proc.apply_memory_limit(previewgen_config.MAX_RENDERER_MEMORY_BYTES)
    extracted_temp: Path | None = None

    try:
        from previewgen.assets import probe_asset

        if source_spec.startswith("zip://"):
            import tempfile
            import urllib.parse
            import zipfile

            from previewgen import limits

            parsed = urllib.parse.urlparse(source_spec)
            zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
            entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
            if not zip_path.is_file() or not entry_name:
                raise ValueError("Invalid zip entry URI")

            extracted_temp = Path(tempfile.mkdtemp(prefix="previewgen_worker_probe_"))
            target_file = extracted_temp / Path(entry_name).name
            with zipfile.ZipFile(zip_path, "r") as zf:
                limits.extract_zip_member_bounded(zf, entry_name, target_file)
            source_path = target_file
        else:
            source_path = Path(source_spec)

        probe_data = probe_asset(source_path)
        result_queue.put({"status": "success", "value": probe_data})
    except Exception as exc:
        with contextlib.suppress(Exception):
            result_queue.put({
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
            })
    finally:
        if extracted_temp and extracted_temp.exists():
            safe_rmtree(extracted_temp, "child worker probe temp")


class ProbeCoordinator:
    """
    Supervises asset probe requests with latest-wins semantics.
    Ensures at most one active probe process and one pending latest request.
    """

    def __init__(self) -> None:
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

    def submit_probe(
        self,
        operation_id: str,
        source: str | Path,
    ) -> None:
        """Submit a probe request. Queues the newest and returns immediately.

        Control-plane call: it never reaps the running worker on the caller
        thread; the supervisor thread observes the pending request and reaps
        off-thread, so the bridge is never blocked. ``source_path`` may be a
        plain path or a ``zip://`` URI; the child worker extracts members itself.
        """
        with self._lock:
            self._pending_task = {
                "operation_id": operation_id,
                "source": str(source),
            }
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
                self._worker_thread.start()

    def cancel_active(self, operation_id: str | None = None) -> None:
        with self._lock:
            if operation_id is None or (
                self._pending_task and self._pending_task.get("operation_id") == operation_id
            ):
                self._pending_task = None

            if operation_id is None or self._active_op_id == operation_id:
                # Signal the supervisor thread; never terminate on the bridge thread.
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

            try:
                res = self._probe_isolated(op_id, source)
                with self._lock:
                    superseded = (
                        self._pending_task is not None
                        or self._active_op_id != op_id
                        or self._cancel_requested
                    )
                if superseded:
                    continue

                if res.get("status") == "success":
                    probe_data = res["value"]
                    if self._dispatch_fn:
                        self._dispatch_fn(
                            "probe.completed",
                            {
                                "operationId": op_id,
                                "probe": probe_data,
                            },
                            op_id,
                        )
                else:
                    if self._dispatch_fn:
                        self._dispatch_fn(
                            "probe.failed",
                            {
                                "operationId": op_id,
                                "error": res.get("error", "Asset probe failed"),
                                "code": res.get("error_type", "UNKNOWN"),
                            },
                            op_id,
                        )
            except Exception as exc:
                logging.debug("Probe execution notice for %s: %s", op_id, exc)
                if self._dispatch_fn:
                    self._dispatch_fn(
                        "probe.failed",
                        {
                            "operationId": op_id,
                            "error": str(exc),
                            "code": type(exc).__name__,
                        },
                        op_id,
                    )

    def _probe_isolated(self, op_id: str, source: str) -> dict[str, Any]:
        result_queue: Any = mp.Queue()
        p = mp.Process(
            target=_probe_worker,
            args=(source, result_queue),
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

        display_name = Path(source).name or source
        start_t = time.time()
        timeout = DEFAULT_PROBE_TIMEOUT_SECONDS
        while p.is_alive():
            with self._lock:
                superseded = (
                    self._active_op_id != op_id
                    or self._pending_task is not None
                    or self._cancel_requested
                )
            if superseded:
                # Reap off-thread (never under the lock) so control calls stay fast.
                self._terminate_active_worker()
                return {"status": "error", "error": "superseded", "error_type": "CANCELLED"}

            if (time.time() - start_t) > timeout:
                logging.warning("Asset probe timeout for %s after %.1fs", display_name, timeout)
                self._terminate_active_worker()
                return {"status": "error", "error": f"Probe timed out ({timeout}s)", "error_type": "TIMEOUT"}
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
