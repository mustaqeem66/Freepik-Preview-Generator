"""Batch bridge contract tests.

These cover the bridge-level guarantees of a batch run: the run carries one
stable operation id, progress and the terminal event are dispatched with that
id, a superseded run's terminal event is suppressed, cancelling a batch does
not cancel unrelated work, and the terminal payload stays bounded.
"""
from __future__ import annotations

import errno
import json
import re
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.api import DesktopApi, _resolve_export_destination
from previewgen.errors import ErrorCode, classify_exception

pytestmark = pytest.mark.core


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def evaluate_js(self, script: str) -> None:
        self.calls.append(script)


def _envelopes(window: _FakeWindow) -> list[dict]:
    out = []
    for script in window.calls:
        match = re.search(r"window\.__onBridgeEvent\((\{.*\})\)", script)
        assert match, f"not an envelope: {script}"
        out.append(json.loads(match.group(1)))
    return out


@pytest.fixture
def api() -> DesktopApi:
    desktop = DesktopApi()
    desktop._set_window(_FakeWindow())
    try:
        yield desktop
    finally:
        desktop.cleanup()


def _grant(api: DesktopApi, inbox: Path, outbox: Path) -> None:
    api._add_authorized_input_folder(str(inbox))
    api._add_authorized_output_folder(str(outbox))


def test_start_batch_delegates_to_lifecycle_and_emits_progress(api, monkeypatch, tmp_path):
    inbox = tmp_path / "in"
    outbox = tmp_path / "out"
    inbox.mkdir()
    outbox.mkdir()
    _grant(api, inbox, outbox)
    captured: dict = {}

    def fake_start(input_folder, output_folder, cfg, progress_callback, **kwargs):
        captured.update(
            input_folder=input_folder,
            output_folder=output_folder,
            cfg=cfg,
            **kwargs,
        )
        progress_callback(1, 4, "one")

    monkeypatch.setattr(api.lifecycle, "start_batch", fake_start)

    result = api.start_batch(str(inbox), str(outbox), {"overwritePolicy": "skip"})

    assert result["ok"] is True
    assert captured["input_folder"] == inbox
    assert captured["output_folder"] == outbox
    assert captured["cfg"].overwrite_policy == "skip"
    assert captured["operation_id"] == result["operationId"]

    [env] = _envelopes(api._window)
    assert env["event"] == "batch.progress"
    assert env["terminal"] is False
    assert env["payload"] == {"current": 1, "total": 4, "message": "one"}
    assert env["operationId"] == result["operationId"]
    assert env["operationId"].startswith("batch_")


def test_start_batch_refuses_an_unauthorized_output_folder(api, tmp_path):
    inbox = tmp_path / "in"
    outbox = tmp_path / "out"
    inbox.mkdir()
    outbox.mkdir()
    api._add_authorized_input_folder(str(inbox))

    result = api.start_batch(str(inbox), str(outbox), {"overwritePolicy": "skip"})

    assert result["ok"] is False
    assert result["error"] == "UNAUTHORIZED_OUTPUT_PATH"


def test_start_batch_refuses_an_unauthorized_input_folder(api, tmp_path):
    inbox = tmp_path / "in"
    outbox = tmp_path / "out"
    inbox.mkdir()
    outbox.mkdir()
    api._add_authorized_output_folder(str(outbox))

    result = api.start_batch(str(inbox), str(outbox), {"overwritePolicy": "skip"})

    assert result["ok"] is False
    assert result["error"] == "UNAUTHORIZED_INPUT_PATH"


def test_a_real_batch_runs_through_the_lifecycle_and_finishes(api, tmp_path):
    from PIL import Image

    inbox = tmp_path / "in"
    outbox = tmp_path / "out"
    inbox.mkdir()
    outbox.mkdir()
    Image.new("RGBA", (32, 32), (255, 0, 0, 128)).save(inbox / "a.png")
    _grant(api, inbox, outbox)

    result = api.start_batch(str(inbox), str(outbox), {"overwritePolicy": "rename"})
    assert result["ok"] is True

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if any("batch.finished" in call for call in api._window.calls):
            break
        time.sleep(0.05)

    envelopes = _envelopes(api._window)
    finished = [env for env in envelopes if env["event"] == "batch.finished"]
    assert finished, "batch.finished was never dispatched"
    assert finished[0]["terminal"] is True
    assert finished[0]["payload"]["success"] == 1
    assert "files" not in finished[0]["payload"]
    assert (outbox / "a.jpg").is_file()


def test_cancelling_a_batch_before_it_starts_does_not_poison_the_next_batch(api):
    api.cancel_batch()
    assert api.lifecycle.cancel_event.is_set()

    # The next run clears the manager event, so a stale cancel cannot stop it.
    api.lifecycle.start_batch(
        Path("/tmp"),
        Path("/tmp"),
        _config(),
        lambda *args: None,
        is_cancelled=lambda: False,
        operation_id="batch_next",
    )
    assert api.lifecycle.cancel_event.is_set() is False
    api.cancel_batch()


def test_restart_is_non_blocking_and_suppresses_a_superseded_terminal(api, monkeypatch, tmp_path):
    inbox = tmp_path / "in"
    outbox = tmp_path / "out"
    inbox.mkdir()
    outbox.mkdir()
    _grant(api, inbox, outbox)
    release_old = threading.Event()
    old_thread = threading.Thread(target=release_old.wait, args=(5.0,), daemon=True)
    old_thread.start()
    api.lifecycle.batch_thread = old_thread

    captured: dict = {}

    def fake_start(input_folder, output_folder, cfg, progress_callback, **kwargs):
        captured.update(kwargs)
        progress_callback(1, 2, "new batch")

    monkeypatch.setattr(api.lifecycle, "start_batch", fake_start)

    started = time.monotonic()
    result = api.start_batch(str(inbox), str(outbox), {"overwritePolicy": "skip"})
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"restart blocked the bridge thread for {elapsed:.2f}s"
    assert result["ok"] is True
    operation_id = result["operationId"]

    api._window.calls.clear()
    api._on_batch_finished({"success": 1, "cancelled": False}, operation_id)
    [env] = _envelopes(api._window)
    assert env["operationId"] == operation_id
    assert env["event"] == "batch.finished"

    release_old.set()
    old_thread.join(timeout=5)


def test_a_new_batch_supersedes_the_previous_one(api, tmp_path):
    from previewgen.lifecycle import ActiveOperation

    previous = ActiveOperation(operation_id="batch_old", kind="batch_render")
    api.lifecycle._active_batch = previous

    api.lifecycle.start_batch(
        tmp_path,
        tmp_path,
        _config(),
        lambda *args: None,
        is_cancelled=lambda: False,
        operation_id="batch_new",
    )

    assert previous.cancel_event.is_set()
    api.cancel_batch()


def _config():
    from previewgen.config import PreviewConfig

    return PreviewConfig()


def test_cancelling_a_batch_does_not_cancel_previews_or_probes(api):
    from previewgen.lifecycle import ActiveOperation

    preview = ActiveOperation(operation_id="preview_1", kind="preview_render")
    api.lifecycle.register_operation(preview)
    api.lifecycle._active_batch = ActiveOperation(
        operation_id="batch_worker", kind="batch_render"
    )

    api.cancel_batch()

    assert api.lifecycle._active_batch.cancel_event.is_set()
    assert preview.cancel_event.is_set() is False


def test_the_finished_summary_drops_files_caps_errors_and_exposes_the_report(api):
    api._batch_operation_id = "batch_abc123"
    errors = [f"error {i}" for i in range(120)]

    api._on_batch_finished(
        {
            "success": 0,
            "failed": 120,
            "files": [{"source": "a"}],
            "errors": errors,
            "reportJson": "previewgen-report-abc123.json",
        }
    )

    [env] = _envelopes(api._window)
    payload = env["payload"]
    assert "files" not in payload
    assert len(payload["errors"]) == 50
    assert payload["errorCount"] == 120
    assert payload["errorsTruncated"] is True
    assert payload["reportJson"] == "previewgen-report-abc123.json"


@pytest.mark.parametrize(
    "policy,expected_name,skipped",
    [
        ("overwrite", "photo.jpg", False),
        ("skip", "photo.jpg", True),
        ("rename", "photo_copy1.jpg", False),
    ],
)
def test_export_destination_honours_the_overwrite_policy(tmp_path, policy, expected_name, skipped):
    (tmp_path / "photo.jpg").write_bytes(b"existing")

    destination, was_skipped = _resolve_export_destination(tmp_path, "photo", policy)

    assert destination.name == expected_name
    assert was_skipped is skipped


def test_export_skip_with_a_corrupt_existing_jpg_still_reports_skip(tmp_path):
    from PIL import Image

    source = tmp_path / "asset.png"
    Image.new("RGBA", (16, 16), (0, 0, 255, 255)).save(source)
    (tmp_path / "asset.jpg").write_bytes(b"definitely not a jpeg")

    api = DesktopApi()
    api._authorized_files.add(source.resolve())
    api._add_authorized_output_folder(str(tmp_path))
    try:
        response = api.export_preview(
            str(source), {"outputFolder": str(tmp_path), "overwritePolicy": "skip"}
        )

        assert response["ok"] is True
        value = response["value"]
        assert value["skipped"] is True
        assert value["width"] is None
        assert value["height"] is None
    finally:
        api.cleanup()


def test_export_destination_rename_increments_when_the_copy_exists(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"existing")
    (tmp_path / "photo_copy1.jpg").write_bytes(b"existing")

    destination, skipped = _resolve_export_destination(tmp_path, "photo", "rename")

    assert destination.name == "photo_copy2.jpg"
    assert skipped is False


def test_disk_full_classification_covers_errno_winerror_and_text():
    assert classify_exception(OSError(errno.ENOSPC, "no room"))[0] == ErrorCode.DISK_FULL
    assert classify_exception(OSError("Insufficient disk space: needs 10 MB"))[0] == ErrorCode.DISK_FULL

    win = OSError("disk full")
    win.winerror = 112
    assert classify_exception(win)[0] == ErrorCode.DISK_FULL
