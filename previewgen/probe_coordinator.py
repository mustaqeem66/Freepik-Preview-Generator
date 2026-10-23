"""
PreviewGen Asset Probe Isolation and Coordination

Supervises asset metadata probing with asynchronous latest-wins semantics:
- Returns an operationId immediately to pywebview (control plane).
- Runs probe inspection in a single long-lived, killable child process.
- Dispatches probe.completed or probe.failed via the typed event envelope.
- Drops stale requests and reaps the running probe when selection switches.

Queue policy: at most one active probe and one pending request; a newer request
replaces the pending one. There is never an unbounded backlog. The probe worker
is kept warm between jobs and restarted only on crash, timeout, supersede, or
explicit shutdown.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from previewgen import config as previewgen_config
from previewgen.tempfiles import safe_rmtree
from previewgen.worker_slot import WorkerSlot

DEFAULT_PROBE_TIMEOUT_SECONDS = 8.0
_KILL_TIMEOUT_SECONDS = 3.0


def _probe_worker(job_queue: Any, result_queue: Any) -> None:  # pragma: no cover - child process
    """Long-lived child worker: probe assets until killed or sent ``None``."""
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.setsid()

    from previewgen import proc as proc_module

    proc_module.apply_memory_limit(previewgen_config.MAX_RENDERER_MEMORY_BYTES)

    from previewgen.assets import probe_asset

    while True:
        job = job_queue.get()
        if job is None:
            return
        job_id, payload = job
        source_spec = str(payload["source"])
        extracted_temp: Path | None = None
        try:
            if source_spec.startswith("zip://"):
                import tempfile
                import urllib.parse

                from previewgen import limits

                parsed = urllib.parse.urlparse(source_spec)
                zip_path = Path(urllib.parse.unquote(parsed.netloc + parsed.path)).resolve()
                entry_name = urllib.parse.parse_qs(parsed.query).get("entry", [""])[0]
                if not zip_path.is_file() or not entry_name:
                    raise ValueError("Invalid zip entry URI")

                extracted_temp = Path(tempfile.mkdtemp(prefix="previewgen_worker_probe_"))
                target_file = extracted_temp / Path(entry_name).name
                with limits.open_zip_bounded(zip_path) as zf:
                    limits.extract_zip_member_bounded(zf, entry_name, target_file)
                source_path = target_file
            else:
                source_path = Path(source_spec)

            probe_data = probe_asset(source_path)
            result_queue.put({"job_id": job_id, "status": "success", "value": probe_data})
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
                safe_rmtree(extracted_temp, "child worker probe temp")


class ProbeCoordinator:
    """
    Supervises asset probe requests with latest-wins semantics.
    Ensures at most one active probe job and one pending latest request.
    """
    _serializable = False  # never reachable from window.pywebview.api


    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._slot = WorkerSlot(
            _probe_worker,
            name="probe",
            memory_limit_bytes=previewgen_config.MAX_RENDERER_MEMORY_BYTES,
            kill_timeout=_KILL_TIMEOUT_SECONDS,
        )
        self._active_op_id: str | None = None
        self._pending_task: dict[str, Any] | None = None
        self._cancel_requested = False
        self._dispatch_fn: Callable[[str, dict[str, Any], str], None] | None = None
        self._running = True

    def set_dispatch_fn(self, dispatch_fn: Callable[[str, dict[str, Any], str], None]) -> None:
        self._dispatch_fn = dispatch_fn

    def is_busy(self) -> bool:
        """True while a probe is queued or rendering in the worker."""
        with self._lock:
            return self._active_op_id is not None or self._pending_task is not None

    def submit_probe(
        self,
        operation_id: str,
        source: str | Path,
    ) -> None:
        """Submit a probe request. Queues the newest and returns immediately.

        Control-plane call: it never reaps the running worker on the caller
        thread; the supervisor thread observes the pending request and reaps
        off-thread, so the bridge is never blocked. ``source`` may be a plain
        path or a ``zip://`` URI; the child worker extracts members itself.
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
                    res = self._probe_isolated(op_id, task["source"])
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

    def _probe_isolated(self, op_id: str, source: str) -> dict[str, Any]:
        self._slot.ensure_started()
        job_id = self._slot.send({"source": str(source)})

        display_name = Path(str(source)).name or str(source)
        start_t = time.monotonic()
        timeout = DEFAULT_PROBE_TIMEOUT_SECONDS
        while True:
            with self._lock:
                superseded = (
                    self._active_op_id != op_id
                    or self._pending_task is not None
                    or self._cancel_requested
                )
            if superseded:
                # Reap off-thread (never under the lock) so control calls stay fast.
                self._slot.kill()
                return {"status": "error", "error": "superseded", "error_type": "CANCELLED"}

            if (time.monotonic() - start_t) > timeout:
                logging.warning("Asset probe timeout for %s after %.1fs", display_name, timeout)
                self._slot.kill()
                return {"status": "error", "error": f"Probe timed out ({timeout}s)", "error_type": "TIMEOUT"}

            res = self._slot.poll(job_id, timeout=0.04)
            if res is not None:
                return res

            if not self._slot.alive():
                exit_code = self._slot.exitcode
                self._slot.kill()
                return {
                    "status": "error",
                    "error": f"Probe worker exited with code {exit_code}",
                    "error_type": "PROCESS_EXIT",
                }

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
            self._pending_task = None
            self._cancel_requested = True
        self._slot.kill()
        worker = self._worker_thread
        if worker is not None and worker.is_alive():
            with contextlib.suppress(Exception):
                worker.join(timeout=_KILL_TIMEOUT_SECONDS + 1.0)
