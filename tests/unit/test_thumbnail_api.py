"""Exact-file and folder authorization for the visible gallery thumbnail bridge."""
from __future__ import annotations

import pytest

from previewgen.api import DesktopApi
from previewgen.thumbnail_coordinator import MAX_VISIBLE_THUMBNAILS

pytestmark = pytest.mark.core


def test_thumbnail_api_rejects_unselected_paths_and_large_lists(tmp_path, monkeypatch):
    source = tmp_path / "secret.png"
    source.write_bytes(b"dummy")
    api = DesktopApi()
    requests = []
    monkeypatch.setattr(api.thumbnail_coordinator, "request", lambda paths: requests.append(paths) or {})
    try:
        denied = api.request_thumbnails([str(source)])
        assert not denied["ok"]
        assert denied["error"] == "UNAUTHORIZED_THUMBNAIL_SOURCE"
        assert requests == []
        assert not api.request_thumbnails([str(source)] * (MAX_VISIBLE_THUMBNAILS + 1))["ok"]
        assert not api.request_thumbnails([""])["ok"]
        api._add_authorized_input_folder(tmp_path)
        assert api.request_thumbnails([str(source)])["ok"]
        assert requests == [[str(source)]]
    finally:
        api.cleanup()


def test_thumbnail_api_accepts_exactly_selected_file_but_not_its_sibling(tmp_path, monkeypatch):
    art = tmp_path / "selected.png"
    sibling = tmp_path / "private.png"
    art.write_bytes(b"dummy")
    sibling.write_bytes(b"dummy")
    api = DesktopApi()
    monkeypatch.setattr(api.thumbnail_coordinator, "request", lambda paths: {paths[0]: "cached"} if paths else {})
    try:
        with api._authorized_lock:
            api._authorized_files.add(art.resolve())
        assert api.request_thumbnails([str(art)])["value"] == {str(art): "cached"}
        assert api.request_thumbnails([str(sibling)])["error"] == "UNAUTHORIZED_THUMBNAIL_SOURCE"
        assert api.request_thumbnails([]) == {"ok": True, "value": {}, "error": None}
    finally:
        api.cleanup()


def test_thumbnail_zip_member_requires_archive_under_authorized_root(tmp_path, monkeypatch):
    import urllib.parse
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("piece.png", b"fake")
    uri = f"zip://{urllib.parse.quote(archive.resolve().as_posix(), safe='/:')}?entry=piece.png"
    api = DesktopApi()
    monkeypatch.setattr(api.thumbnail_coordinator, "request", lambda paths: {})
    try:
        assert api.request_thumbnails([uri])["error"] == "UNAUTHORIZED_THUMBNAIL_SOURCE"
        api._add_authorized_input_folder(tmp_path)
        assert api.request_thumbnails([uri])["ok"]
        assert api.request_thumbnails([uri.replace("piece.png", "evil.exe")])["ok"] is False
    finally:
        api.cleanup()
