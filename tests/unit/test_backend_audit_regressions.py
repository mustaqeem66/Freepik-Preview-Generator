"""Regressions for the defects found auditing the backend.

Each test pins one failure mode that the suite did not cover: a scan that
never reports a terminal event, a supervisor thread that can queue work for a
worker that is already exiting, a bridge method that answers with a rejected
promise instead of the envelope, an error code that does not exist, a scan
that follows a link out of the folder the user granted, and a temp sweep that
deletes a directory it cannot prove it owns.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.api import DesktopApi
from previewgen.destinations import DestinationError, resolve_output_folder
from previewgen.errors import ErrorCode
from previewgen.preview_coordinator import PreviewCoordinator
from previewgen.scanner import get_scanner
from previewgen.tempfiles import OWNER_MARKER, cleanup_stale_temp_dirs

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
        if match:
            out.append(json.loads(match.group(1)))
    return out


# --- non-UTF-8 filenames -------------------------------------------------

UNDECODABLE = "\udcffbroken.png"


def test_scan_with_an_undecodable_filename_still_finishes(tmp_path):
    """os.walk surrogates-escapes undecodable bytes; that must not wedge the scan.

    Paging measures the row payload with UTF-8 encoding, which used to raise on
    a lone surrogate inside the scan callback, where the exception is swallowed
    -- so the UI never received scan.finished and stayed "scanning" forever.
    """
    api = DesktopApi()
    api._window = _FakeWindow()
    api._scan_paging_enabled = True

    api._on_scan_finished("scan-1", {"files": [{"name": UNDECODABLE, "path": UNDECODABLE}]})

    finished = [e for e in _envelopes(api._window) if e["event"] == "scan.finished"]
    assert finished, f"no terminal scan.finished emitted: {api._window.calls}"
    assert finished[0]["terminal"] is True


def test_scan_page_serves_rows_with_undecodable_filenames():
    api = DesktopApi()
    api._window = _FakeWindow()
    api._scan_paging_enabled = True
    # Large enough to take the paged branch, which is where the rows are cached.
    rows = [{"name": UNDECODABLE, "path": UNDECODABLE, "note": "x" * 12000} for _ in range(3)]
    api._on_scan_finished("scan-2", {"files": rows})

    page = api.get_scan_page("scan-2", 0, 10)

    assert page["ok"] is True, page
    assert page["value"]["files"][0]["path"] == UNDECODABLE


def _create_undecodable_name(directory: Path) -> bool:
    """Return False when the platform cannot hold a name that is invalid UTF-8.

    Only a raw ``bytes`` path through ``dir_fd`` gets it onto disk;
    ``Path.write_bytes`` re-encodes the surrogateescape name and raises
    ``UnicodeEncodeError`` on macOS.
    """
    unsupported = (OSError, UnicodeError, ValueError, NotImplementedError)
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except unsupported:
        return False
    try:
        try:
            fd = os.open(b"\xffbroken.png", os.O_CREAT | os.O_WRONLY, 0o644, dir_fd=dir_fd)
        except unsupported:
            return False
        try:
            os.write(fd, b"not really a png")
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
    return True


def test_scanner_lists_a_file_whose_name_cannot_be_decoded(tmp_path):
    if not _create_undecodable_name(tmp_path):
        pytest.skip("this filesystem cannot store an undecodable filename")

    result = get_scanner().scan_folder(str(tmp_path))

    assert [entry["name"] for entry in result["files"]] == [UNDECODABLE]


# --- supervisor lifetime -------------------------------------------------

class _StubServer:
    def publish_jpeg(self, data: bytes) -> str:  # pragma: no cover - unused
        raise AssertionError("the stubbed render must not reach the server")


def _coordinator() -> PreviewCoordinator:
    coord = PreviewCoordinator(_StubServer())
    coord._dispatch_fn = None
    return coord


def test_supervisor_clears_its_thread_reference_when_it_exits():
    """A doomed supervisor must not look live to the next submit_preview."""
    coord = _coordinator()
    coord._render_isolated = lambda *args: {"status": "success", "jpeg_bytes": b"", "width": 1, "height": 1}

    coord._worker_thread = threading.current_thread()
    coord._pending_task = {
        "operation_id": "op-1", "source": "a.png", "config_dict": {}, "max_dimension": 850,
    }
    coord._run_loop()

    assert coord._worker_thread is None


def test_task_queued_while_the_supervisor_dies_is_still_run():
    """The race: submit sees is_alive() on a thread that is already exiting."""
    coord = _coordinator()
    ran: list[str] = []

    def render_isolated(op_id, *args):
        ran.append(op_id)
        if op_id == "op-1":
            # A request lands in the window between dequeuing the last task
            # and the thread stopping, then this thread is killed outright.
            coord._pending_task = {
                "operation_id": "op-2", "source": "b.png", "config_dict": {}, "max_dimension": 850,
            }
            raise KeyboardInterrupt("simulated abrupt exit")
        return {"status": "cancelled"}

    coord._render_isolated = render_isolated
    coord._worker_thread = threading.current_thread()
    coord._pending_task = {
        "operation_id": "op-1", "source": "a.png", "config_dict": {}, "max_dimension": 850,
    }
    with pytest.raises(KeyboardInterrupt):
        coord._run_loop()

    deadline = time.monotonic() + 5.0
    while "op-2" not in ran and time.monotonic() < deadline:
        time.sleep(0.02)
    coord.shutdown()
    assert "op-2" in ran, "the queued preview was dropped with no consumer left"


# --- bridge envelope contract --------------------------------------------

def test_scan_bridge_methods_answer_with_the_envelope(monkeypatch, tmp_path):
    """A share that vanishes after picking must not reject the page promise."""
    api = DesktopApi()

    def explode(*args, **kwargs):
        raise FileNotFoundError("Input folder does not exist")

    monkeypatch.setattr(api.scanner, "scan_folder", explode)
    monkeypatch.setattr(api.scanner, "start_scan", explode)
    monkeypatch.setattr(api, "_is_authorized_input_path", lambda _p: True)

    sync = api.scan_folder(str(tmp_path))
    started = api.start_scan(str(tmp_path), True)

    assert sync["ok"] is False and "error" in sync, sync
    assert started["ok"] is False and "error" in started, started
    assert api._scan_paging_enabled is False, "a failed start must not leave paging armed"


def test_resolve_output_folder_reports_the_real_error_code(tmp_path):
    """It used to raise AttributeError on a code ErrorCode never defined."""
    with pytest.raises(DestinationError) as raised:
        resolve_output_folder("  ", same_folder=False, same_folder_target=tmp_path)
    assert raised.value.code == ErrorCode.OUTPUT_FOLDER_REQUIRED
    assert resolve_output_folder(None, same_folder=True, same_folder_target=tmp_path) == tmp_path.resolve()


# --- scan containment ----------------------------------------------------

def test_scan_does_not_follow_links_out_of_the_granted_folder(tmp_path):
    outside = tmp_path.parent / "outside-grant"
    outside.mkdir(exist_ok=True)
    (outside / "secret.png").write_bytes(b"private")
    root = tmp_path / "granted"
    root.mkdir()
    (root / "real.png").write_bytes(b"public")
    (root / "link.png").symlink_to(outside / "secret.png")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)

    result = get_scanner().scan_folder(str(root))

    listed = {entry["name"] for entry in result["files"]}
    assert listed == {"real.png"}, f"scan escaped the granted folder: {listed}"


# --- stale temp sweep ----------------------------------------------------

def _aged(directory: Path) -> None:
    stamp = time.time() - 10 * 24 * 3600
    import os
    os.utime(directory, (stamp, stamp))


def test_stale_sweep_removes_only_directories_it_can_prove_are_its_own(tmp_path):
    unmarked = tmp_path / "previewgen_render_1_unmarked"
    unmarked.mkdir()
    _aged(unmarked)

    corrupt = tmp_path / "previewgen_render_2_corrupt-marker"
    corrupt.mkdir()
    (corrupt / OWNER_MARKER).write_text("{ not json", encoding="utf-8")
    _aged(corrupt)

    removed = cleanup_stale_temp_dirs(base=tmp_path, max_age_seconds=3600)

    assert removed == 1, "an unprovable directory was deleted, or a real leak survived"
    assert not unmarked.exists()
    assert corrupt.exists(), "a directory with an unreadable owner marker must be left alone"
