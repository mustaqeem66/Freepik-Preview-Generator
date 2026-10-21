"""Source visualization permissions, bounds, and renderer behavior."""
from __future__ import annotations

import io
import time

import pytest
from PIL import Image

from previewgen.api import DesktopApi
from previewgen.renderers.pipeline import source_preview_jpeg_bytes
from previewgen.thumbnail_coordinator import ThumbnailCoordinator

pytestmark = pytest.mark.core


def test_unbranded_source_is_not_previewgen_diagonal_composition(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGBA", (80, 40), (221, 22, 42, 255)).save(path)
    data, width, height = source_preview_jpeg_bytes(path, max_dimension=64)
    assert (width, height) == (80, 40)
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 64
        top = image.getpixel((2, 2))
        bottom = image.getpixel((image.width - 3, image.height - 3))
        # Both corners should display the actual source red; the branded
        # diagonal split would replace one corner with a background pattern.
        assert top[0] > top[1] * 3
        assert bottom[0] > bottom[1] * 3


def test_source_transparency_is_visualized_on_checkerboard(tmp_path):
    path = tmp_path / "clear.png"
    Image.new("RGBA", (48, 32), (0, 0, 0, 0)).save(path)
    data, _, _ = source_preview_jpeg_bytes(path, max_dimension=48)
    with Image.open(io.BytesIO(data)) as output:
        assert output.getpixel((4, 4)) != output.getpixel((23, 4))


def test_source_render_rejects_unbounded_image_dimension(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGBA", (24, 24), (20, 30, 40, 255)).save(path)
    with pytest.raises(ValueError):
        source_preview_jpeg_bytes(path, max_dimension=851)


def test_source_compare_requires_granted_file_and_rejects_3d(tmp_path, monkeypatch):
    selected = tmp_path / "chosen.png"
    neighbour = tmp_path / "private.png"
    mesh = tmp_path / "model.obj"
    selected.write_bytes(b"placeholder")
    neighbour.write_bytes(b"placeholder")
    mesh.write_bytes(b"placeholder")
    api = DesktopApi()
    received = []
    monkeypatch.setattr(
        api.comparison_coordinator, "request",
        lambda paths: received.append(paths) or ({paths[0]: "cached"} if paths else {}),
    )
    try:
        assert api.request_source_comparison(str(selected))["error"] == "UNAUTHORIZED_SOURCE"
        with api._authorized_lock:
            api._authorized_files.add(selected.resolve())
        assert api.request_source_comparison(str(selected))["value"] == {str(selected): "cached"}
        assert api.request_source_comparison(str(neighbour))["error"] == "UNAUTHORIZED_SOURCE"
        assert api.request_source_comparison(str(mesh))["error"] == "UNSUPPORTED_SOURCE_COMPARISON"
        assert api.request_source_comparison("") == {"ok": True, "value": {}, "error": None}
        assert received == [[str(selected)], []]
    finally:
        api.cleanup()


def test_compare_cache_is_one_item_and_renders_source_only():
    class Server:
        def __init__(self):
            self.index = 0
            self.live = set()

        def publish_jpeg(self, _jpeg):
            self.index += 1
            url = f"http://127.0.0.1:1234/session/{self.index}.jpg"
            self.live.add(url)
            return url

        def retain_jpeg(self, handle):
            return handle in self.live

        def release_jpeg(self, handle, force=False):
            self.live.discard(handle)
            return True

    options = []
    events = []

    def render(path, _config, **kwargs):
        options.append((path, kwargs))
        return {"status": "success", "jpeg_bytes": b"jpeg"}

    server = Server()
    comparison = ThumbnailCoordinator(
        server, render, lambda kind, data, _op: events.append((kind, data)),
        max_visible=1, max_retained=1, max_dimension=850,
        timeout=10.0, event_prefix="comparison", source_only=True,
    )
    try:
        comparison.request(["first.png"])
        deadline = time.monotonic() + 3
        while len(events) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(events) == 1
        assert events[0][0] == "comparison.ready"
        assert options[0][1]["source_only"] is True
        assert options[0][1]["max_dimension"] == 850
        comparison.request(["second.png"])
        deadline = time.monotonic() + 3
        while len(events) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(events) == 2
        assert len(server.live) == 1
    finally:
        comparison.close()
    assert not server.live
