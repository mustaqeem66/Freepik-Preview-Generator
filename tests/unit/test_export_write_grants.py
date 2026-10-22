"""Diagnostics/settings browsing grants never implicitly authorize JPG writes."""
from __future__ import annotations

import pytest
from PIL import Image

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


@pytest.fixture
def api():
    instance = DesktopApi()
    try:
        yield instance
    finally:
        instance.cleanup()


def test_general_folder_grant_is_not_batch_write_permission(api, tmp_path, monkeypatch):
    source = tmp_path / "scanned"
    diagnostic = tmp_path / "logs"
    source.mkdir()
    diagnostic.mkdir()
    Image.new("RGB", (32, 32), "blue").save(source / "art.png")
    api._add_authorized_input_folder(source)
    # This simulates open_diagnostics_folder's general permission only.
    api._add_authorized_folder(diagnostic)
    start_calls = []
    monkeypatch.setattr(
        api.lifecycle, "start_batch", lambda *_args, **_kwargs: start_calls.append(True)
    )
    denied = api.start_batch(str(source), str(diagnostic), {})
    assert denied["ok"] is False
    assert denied["error"] == "UNAUTHORIZED_OUTPUT_PATH"
    assert start_calls == []

    api._add_authorized_output_folder(diagnostic)
    allowed = api.start_batch(str(source), str(diagnostic), {})
    assert allowed["ok"] is True
    assert start_calls == [True]


def test_general_folder_grant_is_not_single_export_write_permission(api, tmp_path, monkeypatch):
    source = tmp_path / "source"
    diagnostic = tmp_path / "internal-settings"
    source.mkdir()
    diagnostic.mkdir()
    art = source / "art.png"
    Image.new("RGB", (32, 32), "red").save(art)
    api._add_authorized_input_folder(source)
    api._add_authorized_folder(diagnostic)
    render_calls = []
    monkeypatch.setattr(
        "previewgen.api.render_file_isolated",
        lambda *_args, **_kwargs: render_calls.append(True),
    )
    denied = api.export_preview(str(art), {"outputFolder": str(diagnostic)})
    assert denied["ok"] is False
    assert denied["error"] == "UNAUTHORIZED_PATH"
    assert render_calls == []


def test_same_input_folder_remains_valid_output_without_explicit_output_grant(api, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    api._add_authorized_input_folder(source)
    assert api._is_authorized_export_destination(source) is True
    assert api._is_authorized_export_destination(source / "subfolder") is True
    assert api._is_authorized_export_destination(source, exact_file=True) is False


def test_exact_selected_file_requires_output_picker_not_general_grant(api, tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    art = source / "art.png"
    art.write_bytes(b"sample")
    with api._authorized_lock:
        api._authorized_files.add(art.resolve())
    api._add_authorized_folder(output)
    denied = api.export_preview(str(art), {"outputFolder": str(output)})
    assert denied["error"] == "UNAUTHORIZED_OUTPUT_PATH"
    api._add_authorized_output_folder(output)
    assert api._is_authorized_export_destination(output, exact_file=True)
