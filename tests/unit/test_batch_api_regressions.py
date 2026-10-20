import json
import re
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from previewgen.api import DesktopApi
from previewgen.config import PreviewConfig
from previewgen.lifecycle import LifecycleManager

pytestmark = pytest.mark.core


class FakeWindow:
    def __init__(self):
        self.events = []

    def evaluate_js(self, script):
        match = re.search(r"window\.__onBridgeEvent\((\{.*\})\)", script)
        if match:
            self.events.append(json.loads(match.group(1)))


def test_cancel_before_start_is_safe():
    api = DesktopApi()
    assert api.cancel_batch()["ok"]


def test_single_export_skip_corrupt_target(tmp_path):
    source = tmp_path / "asset.png"
    output = tmp_path / "asset.jpg"
    Image.new("RGB", (32, 32), "red").save(source)
    output.write_bytes(b"not a valid jpeg")
    api = DesktopApi()
    result = api.export_preview(str(source), {
        "outputFolder": str(tmp_path), "overwritePolicy": "skip"
    })
    assert result["ok"] is True
    assert result["value"]["skipped"] is True
    assert result["value"]["width"] is None
    assert output.read_bytes() == b"not a valid jpeg"


def test_single_export_rename_does_not_overwrite(tmp_path):
    source = tmp_path / "asset.png"
    output = tmp_path / "asset.jpg"
    Image.new("RGB", (32, 32), "red").save(source)
    output.write_bytes(b"existing output")
    api = DesktopApi()
    result = api.export_preview(str(source), {
        "outputFolder": str(tmp_path), "overwritePolicy": "rename"
    })
    assert result["ok"]
    assert result["value"]["path"].endswith("asset_copy1.jpg")
    assert output.read_bytes() == b"existing output"


def test_batch_start_returns_id_and_emits_typed_events(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 32), "red").save(source / "test.png")
    api = DesktopApi()
    window = FakeWindow()
    api.set_window(window)
    response = api.start_batch(str(source), str(tmp_path / "out"), {
        "overwritePolicy": "rename"
    })
    assert response["ok"], response
    assert response["operationId"].startswith("batch_")
    worker = api.lifecycle.batch_thread
    assert worker is not None
    worker.join(timeout=30)
    assert not worker.is_alive()
    progress = [e for e in window.events if e["event"] == "batch.progress"]
    finished = [e for e in window.events if e["event"] == "batch.finished"]
    assert progress
    assert len(finished) == 1
    assert finished[0]["operationId"] == response["operationId"]
    assert "files" not in finished[0]["payload"]
    api.cleanup()


def test_superseding_batch_queues_without_bridge_wait(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_process(_input, output, _config, progress, is_cancelled):
        calls.append(str(output))
        if len(calls) == 1:
            started.set()
            release.wait(timeout=4)
        return {
            "success": 0, "failed": 0, "skipped": 0,
            "planned": 0, "duration": 0,
            "cancelled": is_cancelled(),
        }

    monkeypatch.setattr("previewgen.lifecycle.process_folder", fake_process)
    lifecycle = LifecycleManager()
    completed = []
    lifecycle.start_batch(tmp_path, tmp_path / "first", PreviewConfig(),
        lambda *_: None, lambda: False, operation_id="batch_first",
        finished_callback=lambda summary, op_id: completed.append(op_id))
    assert started.wait(2)
    before = time.monotonic()
    lifecycle.start_batch(tmp_path, tmp_path / "second", PreviewConfig(),
        lambda *_: None, lambda: False, operation_id="batch_second",
        finished_callback=lambda summary, op_id: completed.append(op_id))
    assert time.monotonic() - before < 0.2
    release.set()
    lifecycle.batch_thread.join(timeout=5)
    assert not lifecycle.batch_thread.is_alive()
    assert calls == [str(tmp_path / "first"), str(tmp_path / "second")]
    assert completed == ["batch_second"]


def test_cancel_batch_does_not_cancel_scan_operation():
    from previewgen.lifecycle import ActiveOperation
    lifecycle = LifecycleManager()
    scan = ActiveOperation(operation_id="scan", kind="scan")
    lifecycle.register_operation(scan)
    lifecycle.cancel_batch()
    assert not scan.cancel_event.is_set()
