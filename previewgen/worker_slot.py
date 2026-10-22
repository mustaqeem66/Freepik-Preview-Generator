"""
PreviewGen Persistent Worker Slot

A supervision wrapper around a single long-lived child process. Interactive work
(live preview, asset probing) is dispatched to a slot as jobs over a
multiprocessing queue instead of spawning a fresh process per request. Keeping
one warm worker avoids paying the frozen-app startup cost (executable reload,
module imports, native library load, antivirus inspection, IPC setup) on every
UI interaction, which matters most on Windows.

A slot is (re)spawned lazily on the next job and torn down only when the worker:

* crashes (including exceeding its memory / job limit),
* times out on a job,
* is superseded or cancelled while busy (a synchronous native render cannot be
  pre-empted, so the process is reaped and a clean one is started next time),
* or during explicit shutdown.

The queue policy stays "one active, one pending, latest wins"; this module only
changes *how* the active work is hosted, not how much of it can exist.
"""
from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import queue as queue_module
import sys
import threading
from collections.abc import Callable
from typing import Any

from previewgen import proc


class WorkerSlot:
    """Supervises one persistent, restartable child process."""

    def __init__(
        self,
        target: Callable[[Any, Any], None],
        *,
        name: str,
        memory_limit_bytes: int,
        kill_timeout: float = 3.0,
    ) -> None:
        self._target = target
        self._name = name
        self._memory_limit_bytes = memory_limit_bytes
        self._kill_timeout = kill_timeout
        self._lock = threading.Lock()
        self._process: mp.Process | None = None
        self._job_handle: Any = None
        self._job_queue: Any = None
        self._result_queue: Any = None
        self._next_job_id = 0
        self._spawn_count = 0

    @property
    def spawn_count(self) -> int:
        return self._spawn_count

    @property
    def pid(self) -> int | None:
        with self._lock:
            return self._process.pid if self._process is not None else None

    @property
    def exitcode(self) -> int | None:
        with self._lock:
            return self._process.exitcode if self._process is not None else None

    def alive(self) -> bool:
        with self._lock:
            process = self._process
        return process is not None and process.is_alive()

    def ensure_started(self) -> None:
        """Spawn the worker if it is not already running."""
        with self._lock:
            if self._process is not None and self._process.is_alive():
                return
            self._spawn_unlocked()

    def send(self, payload: dict[str, Any]) -> int:
        """Queue a job on the running worker and return its monotonic job id."""
        with self._lock:
            if self._job_queue is None:
                raise RuntimeError(f"{self._name} worker is not running")
            self._next_job_id += 1
            job_id = self._next_job_id
            self._job_queue.put((job_id, payload))
        return job_id

    def poll(self, job_id: int, timeout: float) -> dict[str, Any] | None:
        """Return the matching job result, or ``None`` if not ready yet."""
        with self._lock:
            result_queue = self._result_queue
        if result_queue is None:
            return None
        try:
            message = result_queue.get(timeout=timeout)
        except (queue_module.Empty, OSError, ValueError):
            return None
        if isinstance(message, dict) and message.get("job_id") == job_id:
            return message
        return None

    def kill(self) -> None:
        """Reap the worker process tree and dispose its queues. Idempotent."""
        with self._lock:
            process = self._process
            job_handle = self._job_handle
            result_queue = self._result_queue
            job_queue = self._job_queue
            self._process = None
            self._job_handle = None
            self._result_queue = None
            self._job_queue = None
        proc.reap_process_tree(process, job_handle, kill_timeout=self._kill_timeout)
        for queue in (result_queue, job_queue):
            if queue is not None:
                with contextlib.suppress(Exception):
                    queue.close()

    def _spawn_unlocked(self) -> None:
        self._job_queue = mp.Queue()
        self._result_queue = mp.Queue()
        # Create the Job Object before starting the child so the window in which
        # the worker can spawn an unmanaged descendant is only the assign() call.
        job_handle = proc.WindowsJob(self._memory_limit_bytes) if sys.platform == "win32" else None
        process = mp.Process(
            target=self._target,
            args=(self._job_queue, self._result_queue),
            daemon=True,
            name=f"previewgen-{self._name}",
        )
        process.start()
        if job_handle is not None:
            if not job_handle.active:
                logging.warning("%s worker has no Job Object; containment is degraded", self._name)
            elif process.pid is None or not job_handle.assign(process.pid):
                logging.warning("Could not assign %s worker to its Job Object", self._name)
        self._process = process
        self._job_handle = job_handle
        self._spawn_count += 1
        logging.info(
            "Started persistent %s worker pid=%s (spawn #%d)",
            self._name,
            process.pid,
            self._spawn_count,
        )
