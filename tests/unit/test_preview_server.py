"""
Unit tests for the loopback preview file server.

Previews must be transferred as URLs (served over loopback) rather than as
base64 payloads through the pywebview JS bridge.
"""
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.preview_server import PreviewFileServer

pytestmark = pytest.mark.core

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"payload" + b"\xff\xd9"


@pytest.fixture()
def server():
    srv = PreviewFileServer()
    yield srv
    srv.stop()


def _get(url: str):
    return urllib.request.urlopen(url, timeout=5)


def test_publish_serves_bytes_over_loopback(server):
    url = server.publish_jpeg(JPEG_BYTES)
    assert url.startswith("http://127.0.0.1:")
    assert server.running

    with _get(url) as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "image/jpeg"
        assert resp.headers["Cache-Control"] == "no-store"
        assert resp.read() == JPEG_BYTES


def test_unknown_token_returns_404(server):
    server.publish_jpeg(JPEG_BYTES)
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(f"http://127.0.0.1:{server._port}/wrong-token/preview_000001.jpg")
    assert err.value.code == 404


def test_path_traversal_is_rejected(server):
    url = server.publish_jpeg(JPEG_BYTES)
    base = url.rsplit("/", 1)[0]
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(f"{base}/..%2f..%2fsettings.v1.json")
    assert err.value.code == 404


def test_stop_removes_temp_directory_and_shuts_down(server):
    server.publish_jpeg(JPEG_BYTES)
    root = server._root
    assert root is not None and root.is_dir()

    server.stop()
    assert not server.running
    assert not root.exists()


def test_publish_prunes_old_previews(server):
    for _ in range(5):
        server.publish_jpeg(JPEG_BYTES)
    files = sorted(server._root.glob("preview_*.jpg"))
    assert len(files) == 2


def test_render_preview_returns_url_not_base64():
    from previewgen.api import DesktopApi

    fixture = PROJECT_ROOT / "tests" / "fixtures" / "sample.jpg"
    if not fixture.is_file():
        pytest.skip("sample.jpg fixture missing")

    api = DesktopApi()
    api._add_authorized_input_folder(fixture.parent)
    try:
        result = api.render_preview(str(fixture), {})
        assert result["ok"] is True, result
        value = result["value"]
        assert "url" in value and "dataUrl" not in value
        assert value["url"].startswith("http://127.0.0.1:")
        with _get(value["url"]) as resp:
            assert resp.status == 200
            assert resp.read(2) == b"\xff\xd8"
    finally:
        api.cleanup()

def test_publish_evicts_by_total_bytes(server, monkeypatch):
    import previewgen.preview_server as ps
    monkeypatch.setattr(ps, "_MAX_TOTAL_BYTES", 500)
    monkeypatch.setattr(ps, "_KEEP_NEWEST", 1)

    server.publish_jpeg(b"\xff\xd8" + b"A" * 600)
    server.publish_jpeg(b"\xff\xd8" + b"B" * 600)

    files = list(server._root.glob("preview_*.jpg"))
    assert len(files) == 1


def test_publish_evicts_by_age(server, monkeypatch):
    import os
    import time

    import previewgen.preview_server as ps
    monkeypatch.setattr(ps, "_MAX_FILE_AGE_SECONDS", 1.0)
    monkeypatch.setattr(ps, "_KEEP_NEWEST", 1)

    server.publish_jpeg(JPEG_BYTES)
    files = sorted(server._root.glob("preview_*.jpg"))
    assert len(files) == 1

    old_time = time.time() - 10.0
    os.utime(files[0], (old_time, old_time))

    server.publish_jpeg(JPEG_BYTES)
    remaining = list(server._root.glob("preview_*.jpg"))
    assert len(remaining) == 1
    assert remaining[0].name.endswith("000002.jpg")


def test_stop_is_terminal_and_does_not_resurrect_the_listener():
    """A late preview request after teardown must not rebind a port."""
    server = PreviewFileServer()
    server.publish_jpeg(JPEG_BYTES)
    server.stop()

    with pytest.raises(RuntimeError, match="stopped"):
        server.publish_jpeg(JPEG_BYTES)

    assert not server.running
    assert server._root is None
    assert server._httpd is None
