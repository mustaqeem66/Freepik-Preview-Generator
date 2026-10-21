"""Security boundary for all pywebview source read entry points."""
from __future__ import annotations

import urllib.parse
import zipfile

import pytest
from PIL import Image

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


@pytest.fixture
def api():
    desktop = DesktopApi()
    try:
        yield desktop
    finally:
        desktop.cleanup()


def test_bridge_reads_require_picker_grants_and_output_grant_is_not_read_grant(
    api, tmp_path, monkeypatch
):
    art = tmp_path / "unselected.png"
    Image.new("RGB", (24, 24), "red").save(art)
    calls = []
    monkeypatch.setattr(
        api.preview_coordinator, "submit_preview",
        lambda **kwargs: calls.append(("preview", kwargs)),
    )
    monkeypatch.setattr(
        api.probe_coordinator, "submit_probe",
        lambda **kwargs: calls.append(("probe", kwargs)),
    )
    api.add_authorized_output_folder(tmp_path)
    assert api._source_read_error(str(art)) == "UNAUTHORIZED_SOURCE"

    denied = [
        api.start_preview(str(art), {}),
        api.render_preview(str(art), {}),
        api.start_probe(str(art)),
        api.probe_asset(str(art)),
        api.calculate_export_dimensions(str(art)),
        api.export_preview(str(art), {}),
    ]
    assert all(not result["ok"] for result in denied)
    assert all(result["error"] == "UNAUTHORIZED_SOURCE" for result in denied)
    assert calls == []
    assert not list(tmp_path.glob("*.jpg"))

    api.add_authorized_input_folder(tmp_path)
    assert api._source_read_error(str(art)) is None
    assert api.start_preview(str(art), {})["ok"] is True
    assert api.start_probe(str(art))["ok"] is True
    assert [kind for kind, _ in calls] == ["preview", "probe"]


def test_selected_file_is_exact_and_grant_revocation_is_immediate(api, tmp_path):
    chosen = tmp_path / "chosen.png"
    sibling = tmp_path / "sibling.png"
    chosen.write_bytes(b"image")
    sibling.write_bytes(b"image")
    with api._authorized_lock:
        api._authorized_files.add(chosen.resolve())
    assert api._source_read_error(str(chosen)) is None
    assert api._source_read_error(str(sibling)) == "UNAUTHORIZED_SOURCE"
    assert api.clear_selected_files()["value"] == 1
    assert api._source_read_error(str(chosen)) == "UNAUTHORIZED_SOURCE"


def test_granted_folder_symlink_must_not_escape_source_root(api, tmp_path):
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    private = outside / "secret.png"
    private.write_bytes(b"private")
    linked = root / "linked.png"
    try:
        linked.symlink_to(private)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    api.add_authorized_input_folder(root)
    assert api._source_read_error(str(linked)) == "UNAUTHORIZED_SOURCE"


def test_zip_member_needs_authorized_archive_and_safe_entry(api, tmp_path, monkeypatch):
    archive = tmp_path / "assets.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("normal/item.png", b"data")
    source = (
        "zip://" + urllib.parse.quote(archive.resolve().as_posix(), safe="/:")
        + "?entry=" + urllib.parse.quote("normal/item.png")
    )
    attempted = []
    monkeypatch.setattr(
        api.preview_coordinator, "submit_preview", lambda **kwargs: attempted.append(kwargs)
    )
    assert api.start_preview(source, {})["error"] == "UNAUTHORIZED_SOURCE"
    assert attempted == []
    api.add_authorized_input_folder(tmp_path)
    assert api.start_preview(source, {})["ok"] is True
    assert len(attempted) == 1

    for bad in ("../private.png", "/absolute.png", "nested\\..\\evil.png", "malware.exe"):
        uri = source.split("?entry=")[0] + "?entry=" + urllib.parse.quote(bad)
        assert api.start_preview(uri, {})["error"] == "INVALID_SOURCE"


def test_arbitrary_scan_path_never_grants_itself(api, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        api.scanner, "start_scan", lambda path: calls.append(path) or {"ok": True, "scanId": "ok"}
    )
    folder = str(tmp_path)
    assert api.start_scan(folder)["error"] == "UNAUTHORIZED_INPUT_PATH"
    assert api.scan_folder(folder)["error"] == "UNAUTHORIZED_INPUT_PATH"
    assert api.save_settings({"inputFolder": folder})["error"] == "UNAUTHORIZED_INPUT_PATH"
    assert calls == []
    api.add_authorized_input_folder(folder)
    assert api.start_scan(folder)["ok"] is True
    assert calls == [folder]


def test_saved_auxiliary_paths_require_logo_or_font_picker_grant(api, tmp_path):
    logo = tmp_path / "brand.png"
    font = tmp_path / "custom.otf"
    logo.write_bytes(b"logo")
    font.write_bytes(b"font")
    assert api._auxiliary_read_error({"logoPath": str(logo)}) == "UNAUTHORIZED_AUXILIARY_PATH"
    assert api._auxiliary_read_error({"fontPath": str(font)}) == "UNAUTHORIZED_AUXILIARY_PATH"
    assert api.start_preview(str(logo), {"fontPath": str(font)})["ok"] is False
    with api._authorized_lock:
        api._authorized_auxiliary_files.update({logo.resolve(), font.resolve()})
    assert api._auxiliary_read_error({"logoPath": str(logo), "fontPath": str(font)}) is None
    assert api._auxiliary_read_error({"logoPath": str(logo), "fontPath": str(tmp_path / "other.otf")}) == (
        "UNAUTHORIZED_AUXILIARY_PATH"
    )
