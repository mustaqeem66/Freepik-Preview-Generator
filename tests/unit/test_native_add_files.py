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
        assert not api.is_authorized_output_path(source.parent)
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
        api.add_authorized_output_folder(tmp_path / "out")
        result = api.start_batch_files([str(intruder)], str(tmp_path / "out"), {})
        assert result["error"] == "UNAUTHORIZED_SELECTED_FILE"
        api.add_authorized_folder(tmp_path)
        result = api.start_batch_files([str(source)], str(tmp_path), {})
        # Even explicitly selected SOURCE folders are not output grants for
        # the exact-file multi-directory workflow.
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
        api.add_authorized_output_folder(output)
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


def test_raw_zip_is_rejected_in_file_picker_until_member_preview_is_supported(tmp_path, monkeypatch):
    archive = tmp_path / "artwork.zip"
    archive.write_bytes(b"not a previewable raw asset")
    api = DesktopApi()
    try:
        result, _ = _grant(api, monkeypatch, [archive])
        assert result["ok"]
        assert result["value"]["files"] == []
        assert "choose its folder" in result["value"]["rejected"][0]
        assert not api.is_authorized_selected_file(archive)
    finally:
        api.cleanup()


def test_duplicate_basename_sources_keep_independent_batch_outputs(tmp_path, monkeypatch):
    import json

    dirs = [tmp_path / "first", tmp_path / "second"]
    for folder in dirs:
        folder.mkdir()
        Image.new("RGB", (16, 16), "blue").save(folder / "same.png")
    output = tmp_path / "export"
    output.mkdir()
    api = DesktopApi()
    try:
        sources = [folder / "same.png" for folder in dirs]
        selected, _ = _grant(api, monkeypatch, sources)
        assert len(selected["value"]["files"]) == 2
        api.add_authorized_output_folder(output)
        started = api.start_batch_files([str(source) for source in sources], str(output), {})
        assert started["ok"], started
        worker = api.lifecycle.batch_thread
        assert worker is not None
        worker.join(timeout=45)
        assert not worker.is_alive()
        jpg_files = list(output.glob("*.jpg"))
        assert len(jpg_files) == 2
        payloads = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in output.glob("previewgen-report-*.json")
            if path.name != "previewgen-report-latest.json"
        ]
        assert payloads
        reported = {rec["source"] for rec in payloads[0]["files"]}
        assert reported == {str(source) for source in sources}
    finally:
        api.cleanup()


def test_settings_cannot_launder_a_new_output_grant(tmp_path, monkeypatch):
    """Saving an arbitrary outputFolder must not turn into a trusted picker grant."""
    api = DesktopApi()
    output = tmp_path / "private"
    output.mkdir()
    saved = []
    monkeypatch.setattr("previewgen.api.save_settings", lambda value: saved.append(value) or True)
    try:
        denied = api.save_settings({"outputFolder": str(output), "revision": 1})
        assert not denied["ok"]
        assert denied["error"] == "UNAUTHORIZED_OUTPUT_PATH"
        assert saved == []
        assert not api.is_authorized_output_path(output)

        # Output selections are supported, but only after the native picker
        # (or a separately reviewed restored preference) grants that path.
        api.add_authorized_output_folder(output)
        accepted = api.save_settings({"outputFolder": str(output), "revision": 2})
        assert accepted["ok"]
        assert saved == [{"outputFolder": str(output), "revision": 2}]
    finally:
        api.cleanup()


def test_picked_asset_single_export_requires_explicit_output_grant(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    art = source / "art.png"
    Image.new("RGB", (24, 24), "green").save(art)
    output = tmp_path / "chosen-output"
    output.mkdir()
    api = DesktopApi()
    try:
        result, _ = _grant(api, monkeypatch, [art])
        assert result["ok"]
        # A source-folder grant from another operation is not a destination
        # grant for an Add Files source, even when both refer to the same path.
        api.add_authorized_folder(source)
        denied = api.export_preview(str(art), {"outputFolder": str(source)})
        assert not denied["ok"]
        assert denied["error"] == "UNAUTHORIZED_OUTPUT_PATH"
        assert not (source / "art.jpg").exists()

        api.add_authorized_output_folder(output)
        allowed = api.export_preview(str(art), {
            "outputFolder": str(output), "overwritePolicy": "rename"
        })
        assert allowed["ok"], allowed
        assert (output / "art.jpg").is_file()
    finally:
        api.cleanup()


def test_clearing_collection_revokes_picker_read_capabilities(tmp_path, monkeypatch):
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    Image.new("RGB", (12, 12), "red").save(first)
    Image.new("RGB", (12, 12), "blue").save(second)
    api = DesktopApi()
    try:
        picked, _ = _grant(api, monkeypatch, [first, second])
        assert len(picked["value"]["files"]) == 2
        assert api.is_authorized_selected_file(first)
        assert api.is_authorized_selected_file(second)
        result = api.clear_selected_files()
        assert result == {"ok": True, "value": 2, "error": None}
        assert not api.is_authorized_selected_file(first)
        assert not api.is_authorized_selected_file(second)
        assert api.clear_selected_files()["value"] == 0
        output = tmp_path / "output"
        api.add_authorized_output_folder(output)
        denied = api.start_batch_files([str(first)], str(output), {})
        assert denied["error"] == "UNAUTHORIZED_SELECTED_FILE"
    finally:
        api.cleanup()
