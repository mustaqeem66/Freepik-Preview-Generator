"""
Unit tests for preview retention and explicit release.

Previews are cached on disk by the loopback server. Retention is bounded by
three composite limits (newest count, total bytes, maximum age) and superseded
frames can be explicitly released by the frontend so obsolete renders never
accumulate.
"""
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import preview_server as preview_server_module
from previewgen.preview_server import PreviewFileServer

pytestmark = pytest.mark.core

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"payload" + b"\xff\xd9"


@pytest.fixture()
def server():
    srv = PreviewFileServer()
    yield srv
    srv.stop()


def _previews(server: PreviewFileServer) -> list[Path]:
    assert server._root is not None
    return sorted(server._root.glob("preview_*.jpg"))


def test_eviction_by_newest_count(server, monkeypatch):
    monkeypatch.setattr(preview_server_module, "_KEEP_NEWEST", 2)
    for _ in range(5):
        server.publish_jpeg(JPEG_BYTES)

    files = _previews(server)
    assert len(files) == 2
    assert [p.name for p in files] == ["preview_000004.jpg", "preview_000005.jpg"]


def test_eviction_by_total_bytes(server, monkeypatch):
    monkeypatch.setattr(preview_server_module, "_KEEP_NEWEST", 10)
    monkeypatch.setattr(preview_server_module, "_MAX_TOTAL_BYTES", 100)
    monkeypatch.setattr(preview_server_module, "_MAX_FILE_AGE_SECONDS", 10_000.0)

    chunk = b"\xff\xd8" + b"x" * 38  # 40 bytes per preview
    for _ in range(5):
        server.publish_jpeg(chunk)

    files = _previews(server)
    assert sum(p.stat().st_size for p in files) <= 100
    assert [p.name for p in files] == ["preview_000004.jpg", "preview_000005.jpg"]


def test_eviction_by_age(server, monkeypatch):
    monkeypatch.setattr(preview_server_module, "_KEEP_NEWEST", 10)
    monkeypatch.setattr(preview_server_module, "_MAX_TOTAL_BYTES", 10**9)
    monkeypatch.setattr(preview_server_module, "_MAX_FILE_AGE_SECONDS", 60.0)

    first_url = server.publish_jpeg(JPEG_BYTES)
    server.publish_jpeg(JPEG_BYTES)
    first_name = first_url.rsplit("/", 1)[-1]
    assert server._root is not None
    stale_path = server._root / first_name
    assert stale_path.is_file()

    # Backdate the first preview beyond the age limit, then publish again.
    old = time.time() - 3600
    os.utime(stale_path, (old, old))
    server.publish_jpeg(JPEG_BYTES)

    files = _previews(server)
    assert not stale_path.exists()
    assert len(files) == 2


def test_release_jpeg_deletes_published_file(server):
    url = server.publish_jpeg(JPEG_BYTES)
    assert server._root is not None
    target = server._root / url.rsplit("/", 1)[-1]
    assert target.is_file()

    assert server.release_jpeg(url) is True
    assert not target.exists()
    # Releasing the same (now deleted) frame is a no-op.
    assert server.release_jpeg(url) is False


def test_release_jpeg_rejects_foreign_token_and_traversal(server):
    url = server.publish_jpeg(JPEG_BYTES)
    assert server.release_jpeg(f"http://127.0.0.1:{server._port}/wrong-token/preview_000001.jpg") is False
    base = f"http://127.0.0.1:{server._port}/{server._token}"
    assert server.release_jpeg(f"{base}/..%2f..%2fsettings.v1.json") is False
    # A well-formed but non-existent preview is not an error.
    assert server.release_jpeg(f"{base}/preview_999999.jpg") is False
    # The legitimate file is untouched by the rejected attempts.
    assert server._root is not None
    assert (server._root / url.rsplit("/", 1)[-1]).is_file()


def test_shared_preview_survives_until_last_release(server):
    url = server.publish_jpeg(JPEG_BYTES)
    assert server._root is not None
    target = server._root / url.rsplit("/", 1)[-1]

    # A second consumer takes a reference on the same handle.
    assert server.retain_jpeg(url) is True
    # First release only drops the count; the file must remain for consumer B.
    assert server.release_jpeg(url) is False
    assert target.is_file()
    # Last release removes the file.
    assert server.release_jpeg(url) is True
    assert not target.exists()


def test_release_accepts_bare_handle_id(server):
    url = server.publish_jpeg(JPEG_BYTES)
    handle_id = url.rsplit("/", 1)[-1]
    assert server._root is not None
    assert server.release_jpeg(handle_id) is True
    assert not (server._root / handle_id).exists()


def test_retain_rejects_missing_or_foreign_handle(server):
    url = server.publish_jpeg(JPEG_BYTES)
    assert server.retain_jpeg(f"http://127.0.0.1:{server._port}/wrong-token/preview_000001.jpg") is False
    assert server.retain_jpeg(f"http://127.0.0.1:{server._port}/{server._token}/preview_999999.jpg") is False
    # The legitimate handle still has exactly its publisher reference.
    assert server.release_jpeg(url) is True


def test_retained_preview_survives_count_eviction(server, monkeypatch):
    monkeypatch.setattr(preview_server_module, "_KEEP_NEWEST", 1)
    url_a = server.publish_jpeg(JPEG_BYTES)
    handle_a = url_a.rsplit("/", 1)[-1]
    assert server.retain_jpeg(url_a) is True

    # Publishing more frames would normally evict the oldest by count.
    server.publish_jpeg(JPEG_BYTES)
    server.publish_jpeg(JPEG_BYTES)

    assert server._root is not None
    assert (server._root / handle_a).is_file(), "a retained preview must not be evicted"

    # Releasing both references then allows eviction/deletion.
    assert server.release_jpeg(url_a) is False
    assert (server._root / handle_a).is_file()
    assert server.release_jpeg(handle_a) is True
    assert not (server._root / handle_a).exists()


def test_release_jpeg_before_start_is_noop():
    srv = PreviewFileServer()
    assert srv.release_jpeg("http://127.0.0.1:1/token/preview_000001.jpg") is False


def test_api_release_preview_removes_file_and_invalidates_url():
    from previewgen.api import DesktopApi

    api = DesktopApi()
    try:
        url = api.preview_server.publish_jpeg(JPEG_BYTES)
        response = api.release_preview(url)
        assert response["ok"] is True
        assert response["value"] is True

        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(url, timeout=5)
        assert err.value.code == 404

        invalid = api.release_preview("")
        assert invalid["ok"] is False
        assert invalid["value"] is False
    finally:
        api.cleanup()
