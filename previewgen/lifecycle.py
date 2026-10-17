"""
PreviewGen Lifecycle Module
Orderly shutdown sequence for workers, file writes, and temp directories.
GUI-independent - no webview imports.
"""
from __future__ import annotations
import logging
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from processor import (
    process_folder,
    PreviewConfig,
)


class LifecycleManager:
    """
    Manages application lifecycle, worker threads, and orderly shutdown.
    GUI-independent.
    """
    
    def __init__(self) -> None:
        self.cancel_event = threading.Event()
        self.batch_thread: Optional[threading.Thread] = None
        self.scanner = None  # Set by DesktopApi after creation
        self.session_zip_dir: Optional[Path] = None

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
                    fail_summary = {
                        "planned": 1,
                        "processed": 0,
                        "success": 0,
                        "failed": 1,
                        "skipped": 0,
                        "cancelled": False,
                        "errors": [str(e)],
                        "duration": 0.0,
                    }
                    self._finished_callback(fail_summary)

        self.batch_thread = threading.Thread(target=run_worker, daemon=True)
        self.batch_thread.start()

    def cancel_batch(self) -> None:
        """Signal active batch to cancel."""
        self.cancel_event.set()
        if self.scanner:
            self.scanner.cancel_scan()

    def cleanup(self) -> None:
        """Orderly shutdown sequence for workers, file writes, and temp directories."""
        logging.info("Initiating orderly lifecycle shutdown sequence...")
        
        # 1. Signal cancellation to all workers
        self.cancel_event.set()
        if self.scanner:
            self.scanner.cancel_scan()

        # 2. Wait bounded time for batch thread
        if self.batch_thread and self.batch_thread.is_alive():
            logging.info("Waiting for batch thread termination...")
            self.batch_thread.join(timeout=2.0)

        # 3. Wait bounded time for scan thread (via scanner)
        if self.scanner and hasattr(self.scanner, 'active_scan_thread'):
            scan_t = self.scanner.active_scan_thread
            if scan_t and scan_t.is_alive():
                logging.info("Waiting for scan thread termination...")
                scan_t.join(timeout=1.0)

        # 4. Clean session directories with logging
        if self.scanner and hasattr(self.scanner, 'active_scan_context'):
            if self.scanner.active_scan_context and self.scanner.active_scan_context.temp_root.exists():
                try:
                    shutil.rmtree(self.scanner.active_scan_context.temp_root)
                except Exception as clean_err:
                    logging.warning("Shutdown scan temp cleanup notice: %s", clean_err)

        if self.session_zip_dir and self.session_zip_dir.exists():
            try:
                shutil.rmtree(self.session_zip_dir)
            except Exception as clean_err:
                logging.warning("Shutdown session temp cleanup notice: %s", clean_err)
        
        logging.info("Orderly lifecycle shutdown complete.")

    # Callback for batch completion (set by DesktopApi)
    _finished_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_batch_finished_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._finished_callback = callback