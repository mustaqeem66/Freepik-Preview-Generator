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
    api.add_authorized_folder(tmp_path)  # Simulates the user-selected root from the folder picker
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
    api.add_authorized_folder(tmp_path)
    result = api.export_preview(str(source), {
        "outputFolder": str(tmp_path), "overwritePolicy": "rename"
    })
    assert result["ok"]
    assert result["value"]["path"].endswith("asset_copy1.jpg")
    assert output.read_bytes() == b"existing output"


def test_single_export_rejects_unauthorized_output(tmp_path):
    source = tmp_path / "asset.png"
    Image.new("RGB", (32, 32), "red").save(source)
    outside = tmp_path.parent / f"unauthorized_out_{tmp_path.name}"
    api = DesktopApi()
    result = api.export_preview(str(source), {"outputFolder": str(outside)})
    assert result["ok"] is False
    assert result["error"] == "UNAUTHORIZED_PATH"
    assert not outside.exists()


def test_single_export_same_folder_requires_authorized_source_root(tmp_path):
    source = tmp_path / "asset.png"
    Image.new("RGB", (32, 32), "red").save(source)
    api = DesktopApi()
    result = api.export_preview(str(source), {})
    assert result["ok"] is False
    assert result["error"] == "UNAUTHORIZED_PATH"
    api.add_authorized_folder(tmp_path)
    result = api.export_preview(str(source), {})
    assert result["ok"] is True, result
    assert (tmp_path / "asset.jpg").is_file()


def test_batch_start_returns_id_and_emits_typed_events(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 32), "red").save(source / "test.png")
    api = DesktopApi()
    # Simulate user-authorized source and output chooser roots.
    api.add_authorized_folder(source)
    api.add_authorized_folder(tmp_path / "out")
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


def test_single_export_zip_member_defaults_to_archive_folder(tmp_path):
    """A zip:// member must export next to the archive, not into the temp dir."""
    import urllib.parse
    import zipfile

    member = tmp_path / "asset.png"
    Image.new("RGB", (32, 32), "red").save(member)
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(member, "asset.png")
    member.unlink()

    uri = f"zip://{urllib.parse.quote(archive.as_posix(), safe='/:')}?entry=asset.png"
    api = DesktopApi()
    api.add_authorized_folder(tmp_path)
    result = api.export_preview(uri, {})
    assert result["ok"] is True, result
    assert Path(result["value"]["path"]).parent == tmp_path


def test_single_export_is_visible_as_outstanding_work(tmp_path, monkeypatch):
    """The bridge watchdog needs exports counted as work, or a hung export is silent."""
    seen = []

    def fake_render(_source, dest, _cfg, **_kwargs):
        seen.append(api.has_outstanding_work())
        Image.new("RGB", (16, 16), "blue").save(dest, format="JPEG")

    monkeypatch.setattr("previewgen.api.render_file_isolated", fake_render)
    source = tmp_path / "asset.png"
    Image.new("RGB", (32, 32), "red").save(source)

    api = DesktopApi()
    api.add_authorized_folder(tmp_path)
    assert api.has_outstanding_work() is False
    result = api.export_preview(str(source), {})
    assert result["ok"] is True, result
    assert seen == [True]
    assert api.has_outstanding_work() is False
    assert api.lifecycle.get_active_operations() == []



def test_batch_rejects_destination_not_selected_by_user(tmp_path):
    """Batch must not silently grant arbitrary output write capability."""
    source = tmp_path / "source"
    destination = tmp_path / "private" / "exports"
    source.mkdir()
    destination.parent.mkdir()
    api = DesktopApi()
    api.add_authorized_folder(source)
    try:
        response = api.start_batch(str(source), str(destination), {"overwritePolicy": "rename"})
        assert response["ok"] is False
        assert response["error"] == "UNAUTHORIZED_OUTPUT_PATH"
        assert not destination.exists()
        assert not api.is_authorized_path(destination)
    finally:
        api.cleanup()


def test_batch_allows_output_after_explicit_folder_authorization(tmp_path, monkeypatch):
    """A selected export destination remains usable; no implicit grant needed."""
    source = tmp_path / "source"
    destination = tmp_path / "exports"
    source.mkdir()
    destination.mkdir()
    api = DesktopApi()
    api.add_authorized_folder(source)
    api.add_authorized_folder(destination)
    response = api.start_batch(str(source), str(destination), {"overwritePolicy": "rename"})
    assert response["ok"] is True, response
    api.lifecycle.batch_thread.join(timeout=30)
    assert not api.lifecycle.batch_thread.is_alive()
    api.cleanup()
