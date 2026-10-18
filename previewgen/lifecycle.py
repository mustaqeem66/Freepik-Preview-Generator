"""
PreviewGen Lifecycle Module
Orderly shutdown sequence for workers, file writes, and temp directories.
GUI-independent - no webview imports.
"""
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from previewgen.errors import classify_exception
from previewgen.tempfiles import safe_rmtree
from processor import (
    PreviewConfig,
    process_folder,
)


@dataclass
class ActiveOperation:
    """Central tracking record for an active asynchronous operation."""

    operation_id: str
    kind: str  # "scan", "asset_probe", "preview_render", "batch_render", "archive_extraction"
    state: str = "running"  # "running", "cancelled", "completed", "failed"
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    process_ids: set[int] = field(default_factory=set)
    temp_roots: set[Path] = field(default_factory=set)
    lock_handles: list[Any] = field(default_factory=list)
    cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)


class OperationRegistry:
    """Central thread-safe registry for all in-flight asynchronous operations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._operations: dict[str, ActiveOperation] = {}

    def register(self, op: ActiveOperation) -> None:
        with self._lock:
            self._operations[op.operation_id] = op

    def unregister(self, operation_id: str) -> None:
        with self._lock:
            self._operations.pop(operation_id, None)

    def get(self, operation_id: str) -> ActiveOperation | None:
        with self._lock:
            return self._operations.get(operation_id)

    def all_operations(self) -> list[ActiveOperation]:
        with self._lock:
            return list(self._operations.values())

    def cancel_all(self) -> None:
        with self._lock:
            for op in self._operations.values():
                op.cancel_event.set()
                op.state = "cancelled"

class LifecycleManager:
    """
    Manages application lifecycle, worker threads, and orderly shutdown.
    GUI-independent.
    """

    def __init__(self) -> None:
        self.cancel_event = threading.Event()
        self.batch_thread: threading.Thread | None = None
        self.scanner = None  # Set by DesktopApi after creation
        self.session_zip_dir: Path | None = None
        self.registry = OperationRegistry()

    def register_operation(self, op: ActiveOperation) -> None:
        """Register an active operation with the central lifecycle registry."""
        self.registry.register(op)

    def unregister_operation(self, operation_id: str) -> None:
        """Unregister an operation upon normal completion."""
        self.registry.unregister(operation_id)

    def get_active_operations(self) -> list[ActiveOperation]:
        """Return a snapshot of currently active registered operations."""
        return self.registry.all_operations()
    def set_scanner(self, scanner: Any) -> None:
        """Set scanner reference after it's created."""
        self.scanner = scanner

    def start_batch(
        self,
        input_folder: Path,
        output_folder: Path,
        config: PreviewConfig,
        progress_callback: Callable[[int, int, str], None],
        is_cancelled: Callable[[], bool],
    ) -> None:
        """Start asynchronous batch processing on a dedicated worker thread."""
        self.cancel_event.clear()

        def run_worker() -> None:
            def on_progress(cur: int, tot: int, msg: str) -> None:
                progress_callback(cur, tot, msg)

            try:
                summary = process_folder(
                    input_folder,
                    output_folder,
                    config,
                    on_progress,
                    is_cancelled,
                )
                # Send completion summary
                if self._finished_callback:
                    self._finished_callback(summary)
            except Exception as e:
                logging.exception("Batch execution failed")
                if self._finished_callback:
                    code, message = classify_exception(e)
                    self._finished_callback({
                        "planned": 0, "processed": 0, "remaining": 0,
                        "success": 0, "failed": 0, "skipped": 0,
                        "cancelled": False, "status": "failed",
                        "errorCode": code, "errors": [message], "duration": 0.0,
                    })

        op = ActiveOperation(
            operation_id="batch_worker",
            kind="batch_render",
            cancel_event=self.cancel_event,
        )
        self.batch_thread = threading.Thread(target=run_worker, daemon=True)
        op.thread = self.batch_thread
        self.registry.register(op)
        self.batch_thread.start()
    def cancel_batch(self) -> None:
        """Signal active batch to cancel."""
        self.cancel_event.set()
        self.registry.cancel_all()
        if self.scanner:
            self.scanner.cancel_scan()
    def cleanup(self) -> bool:
        """Orderly shutdown sequence with escalation for workers, file writes, and temp directories."""
        logging.info("Initiating orderly lifecycle shutdown sequence...")
        clean_shutdown = True

        # 1. Signal cancellation to all workers and operations
        self.cancel_event.set()
        self.registry.cancel_all()
        if self.scanner:
            self.scanner.cancel_scan()

        # 2. Wait bounded time for batch thread
        if self.batch_thread and self.batch_thread.is_alive():
            logging.info("Waiting for batch thread termination...")
            self.batch_thread.join(timeout=2.0)
            if self.batch_thread.is_alive():
                clean_shutdown = False
                logging.warning(
                    "Batch thread (ident=%s) survived 2.0s bounded wait during shutdown; "
                    "retaining active resources to avoid premature deletion",
                    getattr(self.batch_thread, "ident", "unknown"),
                )
            else:
                self.registry.unregister("batch_worker")

        # 3. Wait bounded time for scan thread (via scanner)
        if self.scanner and hasattr(self.scanner, 'active_scan_thread'):
            scan_t = self.scanner.active_scan_thread
            if scan_t and scan_t.is_alive():
                logging.info("Waiting for scan thread termination...")
                scan_t.join(timeout=1.0)
                if scan_t.is_alive():
                    clean_shutdown = False
                    logging.warning(
                        "Scan thread (ident=%s) survived 1.0s bounded wait during shutdown; "
                        "retaining active scan temp root to avoid premature deletion",
                        getattr(scan_t, "ident", "unknown"),
                    )
                else:
                    self.registry.unregister("scan_worker")

        # 4. Check registry operations and terminate surviving child processes
        surviving_ops = [
            op for op in self.registry.all_operations()
            if (op.thread and op.thread.is_alive()) or op.process_ids
        ]
        if surviving_ops:
            clean_shutdown = False
            for op in surviving_ops:
                logging.warning(
                    "Surviving active operation during shutdown: id=%s kind=%s pids=%s",
                    op.operation_id, op.kind, op.process_ids
                )
                for pid in list(op.process_ids):
                    try:
                        import os
                        import signal
                        os.kill(pid, signal.SIGTERM)
                        logging.info("Signalled SIGTERM to orphaned renderer process pid=%d", pid)
                    except Exception as kill_err:
                        logging.warning(
                            "Could not terminate orphaned renderer process pid=%d for op=%s: %s. "
                            "Manual intervention required.",
                            pid, op.operation_id, kill_err,
                        )

        # 5. Clean session directories with logging ONLY if their owning operations exited cleanly
        active_temp_roots = {root for op in surviving_ops for root in op.temp_roots}

        scan_active = bool(
            self.scanner
            and hasattr(self.scanner, 'active_scan_thread')
            and self.scanner.active_scan_thread
            and self.scanner.active_scan_thread.is_alive()
        )
        if self.scanner and hasattr(self.scanner, 'active_scan_context') and self.scanner.active_scan_context:
            scan_root = self.scanner.active_scan_context.temp_root
            if not scan_active and scan_root not in active_temp_roots:
                safe_rmtree(scan_root, "shutdown scan temp")
            else:
                logging.warning("Retaining active scan temp directory while worker is still running: %s", scan_root)

        batch_active = bool(self.batch_thread and self.batch_thread.is_alive())
        if self.session_zip_dir:
            if not batch_active and self.session_zip_dir not in active_temp_roots:
                safe_rmtree(self.session_zip_dir, "shutdown session temp")
            else:
                logging.warning(
                    "Retaining session zip temp directory while batch worker is still running: %s",
                    self.session_zip_dir,
                )

        if clean_shutdown:
            logging.info("Orderly lifecycle shutdown complete.")
        else:
            logging.warning("Lifecycle shutdown finished with incomplete worker joins. Resources safely retained.")
        return clean_shutdown
    # Callback for batch completion (set by DesktopApi)
    _finished_callback: Callable[[dict[str, Any]], None] | None = None

    def set_batch_finished_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._finished_callback = callback
