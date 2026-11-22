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


def test_counter_rollover_keeps_numeric_frame_order(server):
    """Past six digits the zero-padded names stop sorting lexicographically."""
    server._counter = 999_997
    for _ in range(3):
        server.publish_jpeg(JPEG_BYTES)

    remaining = {path.name for path in server._root.glob("preview_*.jpg")}
    assert remaining == {"preview_999999.jpg", "preview_1000000.jpg"}


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


def test_preview_published_from_a_worker_thread_is_reachable_over_loopback():
    """A preview published off the main thread must still be fetchable.

    The preview coordinator publishes from its own worker thread, not the
    main thread. On kernels that refuse to route connections to a loopback
    socket bound from a worker thread (WSL2 among them), binding lazily on
    the first publish produced a listener that sat in LISTEN state while
    every connect was answered with ECONNREFUSED: the UI showed
    "Preview unavailable" and the image never loaded.

    The server binds in its constructor, so the socket is created on the
    thread that constructed it. This test drives the production path --
    publish from a worker thread -- and fetches the result.
    """
    import threading

    srv = PreviewFileServer()
    try:
        published: dict[str, str] = {}

        def _publish() -> None:
            published["url"] = srv.publish_jpeg(JPEG_BYTES)

        worker = threading.Thread(target=_publish, name="preview-coordinator-test")
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive(), "the publishing worker did not finish"

        url = published["url"]
        with _get(url) as resp:
            assert resp.status == 200
            assert resp.read() == JPEG_BYTES
    finally:
        srv.stop()


def test_a_failed_bind_does_not_leave_an_orphaned_session_directory(monkeypatch):
    """A bind that cannot succeed must not strand the session temp directory.

    The session directory is created before the socket is bound, so a bind
    failure has to take the directory down again. Otherwise every failed
    start leaves an orphaned temp directory on disk.
    """
    import previewgen.preview_server as preview_server_module

    created: list = []
    real_create = preview_server_module.create_temp_dir

    def _track(prefix: str):
        path = real_create(prefix)
        created.append(path)
        return path

    def _fail_bind(*args, **kwargs):
        raise OSError("no ephemeral ports available")

    monkeypatch.setattr(preview_server_module, "create_temp_dir", _track)
    monkeypatch.setattr(preview_server_module, "_PreviewHTTPServer", _fail_bind)

    with pytest.raises(OSError, match="no ephemeral ports available"):
        PreviewFileServer()

    assert created, "the session directory was never created"
    for path in created:
        assert not path.exists(), f"the failed bind left {path} behind"


def test_binding_the_preview_server_never_performs_a_reverse_dns_lookup(monkeypatch):
    """Publishing a preview must not depend on a DNS resolver answering.

    ``HTTPServer.server_bind`` calls ``socket.getfqdn`` to fill in the
    canonical name it puts in the access log. That is a reverse DNS lookup,
    and on a host with no answer for the address it blocks until the
    resolver gives up. On the macOS CI runner it held the bind for over
    twenty seconds, which stalled the packaged CSP probe before it could
    reach the WebView at all.

    The server binds to loopback and serves an unguessable token, so the
    canonical name is used for nothing but logging and must not be on the
    path that publishes a preview.
    """
    import socket

    calls: list[str] = []

    def _spy_getfqdn(host: str = ""):
        calls.append(host)
        return "should-not-be-used.example"

    monkeypatch.setattr(socket, "getfqdn", _spy_getfqdn)

    srv = PreviewFileServer()
    try:
        url = srv.publish_jpeg(JPEG_BYTES)
    finally:
        srv.stop()

    assert calls == [], f"the bind performed a reverse lookup: {calls}"
    assert url.startswith("http://127.0.0.1:")
