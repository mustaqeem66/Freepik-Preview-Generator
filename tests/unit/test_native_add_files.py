"""Native Add Files exact-grant and selected batch regressions."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


class FakePicker:
    def __init__(self, selected: list[str]) -> None:
        self.selected = selected
        self.calls: list[tuple[int, bool]] = []

    def create_file_dialog(self, kind: int, *, allow_multiple: bool = False):
        self.calls.append((kind, allow_multiple))
        return self.selected


def _grant(api: DesktopApi, monkeypatch, selected: list[Path]):
    window = FakePicker([str(path) for path in selected])
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(OPEN_DIALOG=1))
    api.set_window(window)
    return api.browse_files(), window


def test_native_picker_grants_individual_paths_only(tmp_path, monkeypatch):
    source = tmp_path / "private" / "one.png"
    source.parent.mkdir()
    Image.new("RGB", (24, 24), "red").save(source)
    neighbour = source.parent / "other.png"
    Image.new("RGB", (24, 24), "green").save(neighbour)
    unsupported = source.parent / "notes.txt"
    unsupported.write_text("hello", encoding="utf-8")
    api = DesktopApi()
    try:
        result, window = _grant(api, monkeypatch, [source, unsupported, source])
        assert result["ok"], result
        assert [entry["name"] for entry in result["value"]["files"]] == ["one.png"]
        assert len(result["value"]["rejected"]) == 1
        assert window.calls == [(1, True)]
        assert api.is_authorized_selected_file(source)
        assert not api.is_authorized_selected_file(neighbour)
        assert not api.is_authorized_path(source.parent)
    finally:
        api.cleanup()


def test_injected_files_and_unauthorized_output_rejected(tmp_path, monkeypatch):
    source = tmp_path / "art.png"
    intruder = tmp_path / "intruder.png"
    Image.new("RGB", (24, 24), "red").save(source)
    Image.new("RGB", (24, 24), "blue").save(intruder)
    api = DesktopApi()
    try:
        picked, _ = _grant(api, monkeypatch, [source])
        assert picked["ok"]
        assert api.start_batch_files([str(intruder)], str(tmp_path), {})["error"] == "UNAUTHORIZED_OUTPUT_PATH"
        api.add_authorized_folder(tmp_path / "out")
        result = api.start_batch_files([str(intruder)], str(tmp_path / "out"), {})
        assert result["error"] == "UNAUTHORIZED_SELECTED_FILE"
        result = api.start_batch_files([str(source)], str(tmp_path), {})
        # The grant to source must never authorize its parent as an output.
        assert result["error"] == "UNAUTHORIZED_OUTPUT_PATH"
    finally:
        api.cleanup()


def test_selected_files_from_two_folders_are_batch_exported(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    output = tmp_path / "exports"
    first.mkdir()
    second.mkdir()
    output.mkdir()
    a = first / "art-a.png"
    b = second / "art-b.png"
    Image.new("RGB", (20, 20), "red").save(a)
    Image.new("RGB", (20, 20), "blue").save(b)
    api = DesktopApi()
    try:
        picked, _ = _grant(api, monkeypatch, [a, b])
        assert picked["ok"], picked
        api.add_authorized_folder(output)
        started = api.start_batch_files(
            [str(a), str(b)], str(output), {"overwritePolicy": "rename"}
        )
        assert started["ok"], started
        thread = api.lifecycle.batch_thread
        assert thread is not None
        thread.join(timeout=45)
        assert not thread.is_alive()
        assert (output / "art-a.jpg").is_file()
        assert (output / "art-b.jpg").is_file()
        assert list(output.glob("previewgen-report-*.json"))
        assert not api.is_authorized_path(first)
        assert not api.is_authorized_path(second)
    finally:
        api.cleanup()
