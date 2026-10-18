"""
Shutdown-in-progress tests.

An orderly shutdown must interrupt work that is mid-flight (discovery, a running
renderer, report writing) without leaving orphaned processes, temp directories,
or partially written reports behind.
"""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch.reporting import write_batch_reports
from previewgen.errors import ErrorCode
from previewgen.lifecycle import LifecycleManager
from previewgen.renderer_process import RendererProcessPool
from previewgen.tempfiles import create_temp_dir
from processor import PreviewConfig

pytestmark = pytest.mark.core

SAMPLE_PNG = PROJECT_ROOT / "tests" / "fixtures" / "sample.png"


class _FakeScanner:
    """Scanner stub whose discovery thread only stops when cancelled."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self.active_scan_context = SimpleNamespace(temp_root=create_temp_dir("previewgen_scan_"))
        self.active_scan_thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.02)

    def start(self) -> None:
        self.active_scan_thread.start()

    def cancel_scan(self) -> None:
        self._stop.set()


def test_cleanup_cancels_active_discovery():
    lifecycle = LifecycleManager()
    scanner = _FakeScanner()
    scanner.start()
    temp_root = scanner.active_scan_context.temp_root

    assert scanner.active_scan_thread.is_alive()
    lifecycle.set_scanner(scanner)

    lifecycle.cleanup()

    assert scanner._stop.is_set()
    assert not scanner.active_scan_thread.is_alive()
    assert not temp_root.exists()


def test_cleanup_joins_running_batch(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    for i in range(60):
        Image.new("RGB", (16, 16), (i % 255, 0, 0)).save(in_dir / f"a{i:03d}.png")

    lifecycle = LifecycleManager()
    summaries: list[dict] = []
    lifecycle.set_batch_finished_callback(lambda summary: summaries.append(summary))

    lifecycle.start_batch(
        in_dir,
        out_dir,
        PreviewConfig(),
        progress_callback=lambda *_a: None,
        is_cancelled=lifecycle.cancel_event.is_set,
    )
    assert lifecycle.batch_thread is not None

    # Shut down immediately while the batch is still running.
    lifecycle.cleanup()

    assert not lifecycle.batch_thread.is_alive()
    assert summaries, "batch completion callback must still fire after shutdown"
    assert summaries[0]["cancelled"] is True


def test_cleanup_terminates_active_renderer(tmp_path):
    if not SAMPLE_PNG.is_file():
        pytest.skip("sample.png fixture missing")

    out = tmp_path / "out.jpg"
    pool = RendererProcessPool(default_timeout=30.0)

    with pytest.raises(RuntimeError):
        # is_cancelled() is True from the first loop iteration, so the live child
        # process is terminated exactly as it would be during shutdown.
        pool.render(SAMPLE_PNG, out, PreviewConfig(), timeout_seconds=30.0, is_cancelled=lambda: True)

    assert pool.last_survivors == set()
    assert not out.exists()
    assert list(tmp_path.glob("previewgen_render_*")) == []


def test_interrupted_report_write_leaves_no_partial_state(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    summary = {"batchId": "deadbeef", "status": "completed"}

    original_replace = Path.replace
    calls = {"n": 0}

    def flaky_replace(self, target):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated crash during report install")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    result = write_batch_reports(out, summary, [])

    assert result["status"] == "failed"
    assert result["errorCode"] == ErrorCode.REPORT_WRITE_FAILED
    # No half-written report or dangling temp files may survive.
    assert not Path(result["jsonPath"]).exists()
    assert not Path(result["latestPath"]).exists()
    assert [p for p in out.iterdir() if p.name.endswith(".tmp")] == []


def test_concurrent_report_writes_never_corrupt_latest_pointer(tmp_path):
    out = tmp_path / "out"
    out.mkdir()

    results: list[dict] = []
    lock = threading.Lock()

    def worker(batch_id: str) -> None:
        result = write_batch_reports(out, {"batchId": batch_id, "status": "completed"}, [])
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(f"batch{i:04d}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 6
    assert all(r["status"] == "written" for r in results)
    assert [p for p in out.iterdir() if p.name.endswith(".tmp")] == []

    latest = out / "previewgen-report-latest.json"
    assert latest.is_file()
    # The pointer must reference an existing, complete report pair.
    import json

    pointer = json.loads(latest.read_text(encoding="utf-8"))
    assert (out / pointer["json"]).is_file()
    assert (out / pointer["csv"]).is_file()

def test_active_operation_registry_and_incomplete_shutdown_escalation(tmp_path):
    """Surviving worker threads must escalate to incomplete shutdown and retain their temp roots."""
    from previewgen.lifecycle import ActiveOperation

    lifecycle = LifecycleManager()
    temp_root = tmp_path / "surviving_scan"
    temp_root.mkdir()
    (temp_root / "partial.tmp").write_bytes(b"data")

    stop_event = threading.Event()

    def lingering_worker():
        # Refuses to stop on cancel_event, only stops on stop_event
        while not stop_event.is_set():
            time.sleep(0.02)

    worker_thread = threading.Thread(target=lingering_worker, daemon=True)
    worker_thread.start()

    op = ActiveOperation(
        operation_id="scan_lingering_001",
        kind="scan",
        thread=worker_thread,
        temp_roots={temp_root},
    )
    lifecycle.register_operation(op)
    assert len(lifecycle.get_active_operations()) == 1

    # Attached mock scanner with surviving thread
    class MockScanner:
        def __init__(self):
            self.active_scan_thread = worker_thread
            self.active_scan_context = SimpleNamespace(temp_root=temp_root)
        def cancel_scan(self):
            pass

    lifecycle.set_scanner(MockScanner())

    # Cleanup must return False (incomplete shutdown) because worker is still alive
    clean_shutdown = lifecycle.cleanup()
    assert clean_shutdown is False

    # Crucial safety check: temp_root must be RETAINED so the live worker does not crash
    assert temp_root.exists()
    assert (temp_root / "partial.tmp").exists()

    # Cleanup lingering thread
    stop_event.set()
    worker_thread.join(timeout=1.0)
