import shutil
import sys
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import limits
from previewgen.api import DesktopApi
from previewgen.preview_coordinator import PreviewCoordinator, _materialize_source
from previewgen.worker_slot import WorkerSlot

pytestmark = pytest.mark.core


def _echo_worker(job_queue, result_queue) -> None:  # module-level so it is picklable
    while True:
        job = job_queue.get()
        if job is None:
            return
        job_id, payload = job
        if payload.get("fail"):
            result_queue.put({
                "job_id": job_id,
                "status": "error",
                "error": "boom",
                "error_type": "ValueError",
            })
        else:
            result_queue.put({"job_id": job_id, "status": "success", "value": payload.get("value")})


def _await_result(slot: WorkerSlot, job_id: int, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = slot.poll(job_id, timeout=0.05)
        if res is not None:
            return res
    raise AssertionError(f"job {job_id} did not complete within {timeout}s")


def _zip_uri(zip_path: Path, entry: str) -> str:
    return f"zip://{urllib.parse.quote(zip_path.as_posix(), safe='/:')}?entry={entry}"


def test_materialize_source_extracts_archive_member(tmp_path):
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("inner/asset.png", b"payload-bytes")

    source, temp_root = _materialize_source(_zip_uri(zip_path, "inner/asset.png"))

    try:
        assert source.read_bytes() == b"payload-bytes"
        assert temp_root is not None and temp_root.exists()
    finally:
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)


def test_materialize_source_returns_plain_path_without_temp(tmp_path):
    asset = tmp_path / "plain.png"
    asset.write_bytes(b"x")

    source, temp_root = _materialize_source(asset)

    assert source == asset.resolve()
    assert temp_root is None


def test_materialize_source_cleans_up_when_extraction_fails(tmp_path, monkeypatch):
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("present.png", b"x")

    created: list[Path] = []
    real_mkdtemp = __import__("tempfile").mkdtemp

    def _tracked_mkdtemp(*args, **kwargs):
        created.append(Path(real_mkdtemp(dir=tmp_path)))
        return str(created[-1])

    monkeypatch.setattr("previewgen.preview_coordinator.tempfile.mkdtemp", _tracked_mkdtemp)

    with pytest.raises(KeyError):
        _materialize_source(_zip_uri(zip_path, "missing.png"))

    assert created, "expected an extraction temp dir to have been created"
    assert not created[0].exists(), "failed extraction must remove its temp dir"


def test_start_preview_defers_extraction_off_the_bridge_thread(tmp_path, monkeypatch):
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("asset.png", b"payload")

    api = DesktopApi()
    submitted: dict = {}

    class _RecordingCoordinator:
        def submit_preview(self, **kwargs):
            submitted.update(kwargs)

    api.preview_coordinator = _RecordingCoordinator()

    def _boom(*args, **kwargs):
        raise AssertionError("archive extraction ran on the pywebview bridge thread")

    monkeypatch.setattr(limits, "extract_zip_member_bounded", _boom)

    uri = _zip_uri(zip_path, "asset.png")
    api._add_authorized_input_folder(tmp_path)
    result = api.start_preview(uri, {}, request_id=7)

    assert result["ok"] is True
    assert result["status"] == "queued"
    assert submitted["source"] == uri
    assert submitted["operation_id"] == "preview_7"


def test_start_preview_rejects_invalid_zip_uri_without_extracting(tmp_path):
    api = DesktopApi()

    result = api.start_preview("zip:///no/such/archive.zip?entry=asset.png", {})

    assert result["ok"] is False
    assert result["error"] == "UNAUTHORIZED_SOURCE"


def test_control_plane_calls_never_block_on_worker_reap(monkeypatch):
    reaped_threads: list[threading.Thread] = []

    def _slow_reap(*args, **kwargs):
        reaped_threads.append(threading.current_thread())
        time.sleep(1.0)

    monkeypatch.setattr("previewgen.proc.terminate_process_tree", _slow_reap)
    coordinator = PreviewCoordinator(object())
    monkeypatch.setattr(
        coordinator,
        "_render_isolated",
        lambda *a, **k: {"status": "error", "error": "stub", "error_type": "STUB"},
    )

    start = time.monotonic()
    coordinator.submit_preview("op-1", "/nope/x.png", {})
    coordinator.cancel_active("op-1")
    elapsed = time.monotonic() - start

    assert elapsed < 0.25, "a control-plane call must not wait on the worker reap"
    assert threading.main_thread() not in reaped_threads


def test_pending_queue_is_bounded_and_latest_wins(monkeypatch):
    coordinator = PreviewCoordinator(object())
    release = threading.Event()
    started = threading.Event()

    def _blocking_render(*args, **kwargs):
        started.set()
        release.wait(5)
        return {"status": "error", "error": "stub", "error_type": "STUB"}

    monkeypatch.setattr(
        "previewgen.preview_coordinator._materialize_source",
        lambda source: (Path("/nope.png"), None),
    )
    monkeypatch.setattr(coordinator, "_render_isolated", _blocking_render)

    coordinator.submit_preview("op-0", "/nope.png", {})
    assert started.wait(5), "supervisor thread never started work"

    for i in range(1, 50):
        coordinator.submit_preview(f"op-{i}", "/nope.png", {})

    # Only one pending slot exists: the newest request wins, no backlog grows.
    assert coordinator._pending_task is not None
    assert coordinator._pending_task["operation_id"] == "op-49"

    release.set()
    coordinator.cancel_active()


def test_worker_slot_reuses_one_warm_process_between_jobs():
    slot = WorkerSlot(_echo_worker, name="test-echo", memory_limit_bytes=0, kill_timeout=2.0)
    try:
        slot.ensure_started()
        first_pid = slot.pid

        first = _await_result(slot, slot.send({"value": "a"}))
        second = _await_result(slot, slot.send({"value": "b"}))

        assert first["value"] == "a"
        assert second["value"] == "b"
        assert slot.spawn_count == 1, "a warm worker must not respawn between jobs"
        assert slot.pid == first_pid
    finally:
        slot.kill()


def test_worker_slot_restarts_only_after_being_reaped():
    slot = WorkerSlot(_echo_worker, name="test-echo", memory_limit_bytes=0, kill_timeout=2.0)
    try:
        slot.ensure_started()
        first_pid = slot.pid
        assert _await_result(slot, slot.send({"value": 1}))["status"] == "success"

        slot.kill()
        assert not slot.alive()

        slot.ensure_started()
        assert slot.pid != first_pid
        assert slot.spawn_count == 2
        assert _await_result(slot, slot.send({"value": 2}))["value"] == 2
    finally:
        slot.kill()


def test_worker_slot_reports_job_errors_without_dying():
    slot = WorkerSlot(_echo_worker, name="test-echo", memory_limit_bytes=0, kill_timeout=2.0)
    try:
        slot.ensure_started()
        failed = _await_result(slot, slot.send({"fail": True}))
        assert failed["status"] == "error"
        assert failed["error_type"] == "ValueError"
        # A Python-level job error must not tear the warm worker down.
        assert slot.alive()
        assert slot.spawn_count == 1
    finally:
        slot.kill()

