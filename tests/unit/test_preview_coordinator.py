import shutil
import sys
import urllib.parse
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import limits
from previewgen.api import DesktopApi
from previewgen.preview_coordinator import _materialize_source

pytestmark = pytest.mark.core


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
    result = api.start_preview(uri, {}, request_id=7)

    assert result["ok"] is True
    assert result["status"] == "queued"
    assert submitted["source"] == uri
    assert submitted["operation_id"] == "preview_7"


def test_start_preview_rejects_invalid_zip_uri_without_extracting(tmp_path):
    api = DesktopApi()

    result = api.start_preview("zip:///no/such/archive.zip?entry=asset.png", {})

    assert result["ok"] is False
    assert "zip" in result["error"].lower()
