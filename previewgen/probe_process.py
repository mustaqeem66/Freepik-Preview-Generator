"""
PreviewGen Asset Probe Process Isolation

Runs asset metadata probing (PSD canvas/layer inspection, mesh complexity scans,
SVG bounds) in an isolated child process with a hard timeout and a best-effort
memory ceiling. Probing parses untrusted creator/proprietary content, so it must
run under the same containment model as rendering: a hostile or malformed file
must be unable to hang or exhaust the main (GUI) process.

Execution model:
    Parent (GUI) process
      -> spawn probe child (own session/process group, memory-limited)
      -> child inspects the asset and returns a small JSON-able dict
      -> parent waits with a hard timeout
      -> timeout: terminate the child tree and raise TimeoutError
"""
from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import os
import queue as queue_module
import sys
import time
from pathlib import Path
from typing import Any

from previewgen import config as previewgen_config
from previewgen import proc

DEFAULT_PROBE_TIMEOUT_SECONDS = 15.0
_KILL_TIMEOUT_SECONDS = 5.0


def _probe_worker(source_path: str, result_queue: Any) -> None:  # pragma: no cover - child process
    """Worker process: probe an asset and report a small result dict."""
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.setsid()
    proc.apply_memory_limit(previewgen_config.MAX_RENDERER_MEMORY_BYTES)
    try:
        from previewgen.assets import probe_asset

        result_queue.put({"status": "success", "value": probe_asset(Path(source_path))})
    except Exception as exc:
        with contextlib.suppress(Exception):
            result_queue.put({
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
            })


def _terminate(process: Any) -> None:
    if process is None or not process.is_alive():
        return
    pid = process.pid
    if pid is not None:
        survivors = proc.terminate_process_tree(pid, kill_timeout=_KILL_TIMEOUT_SECONDS)
        if survivors:
            logging.error("Probe process tree left %d surviving descendant(s)", len(survivors))
    with contextlib.suppress(Exception):
        process.join(timeout=_KILL_TIMEOUT_SECONDS)


def probe_asset_isolated(
    source_path: Path | str,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe an asset in an isolated child process with a hard timeout.

    Returns the probe result dict. Raises ``TimeoutError`` when the probe exceeds
    ``timeout_seconds`` and ``RuntimeError`` on any child failure, so callers fail
    closed rather than trusting an uninspected asset.
    """
    result_queue: Any = mp.Queue()
    process = mp.Process(
        target=_probe_worker,
        args=(str(source_path), result_queue),
        daemon=True,
    )
    process.start()
    try:
        start_time = time.monotonic()
        while process.is_alive():
            if (time.monotonic() - start_time) > timeout_seconds:
                _terminate(process)
                raise TimeoutError(f"Asset probe exceeded {timeout_seconds}s for {Path(source_path).name}")
            time.sleep(0.05)

        process.join(timeout=_KILL_TIMEOUT_SECONDS)

        try:
            result = result_queue.get(timeout=2.0)
        except queue_module.Empty:
            raise RuntimeError(
                f"Asset probe process exited without a result (code {process.exitcode})"
            ) from None

        if result.get("status") == "error":
            raise RuntimeError(
                f"Asset probe failed: {result.get('error')} ({result.get('error_type', 'Unknown')})"
            )
        return result["value"]
    finally:
        _terminate(process)
        with contextlib.suppress(Exception):
            result_queue.close()
            result_queue.join_thread()
