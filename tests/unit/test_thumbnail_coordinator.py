"""Bounded thumbnail rendering tests; no OS window or real renderer is started."""
from __future__ import annotations

import threading
import time

import pytest

from previewgen.thumbnail_coordinator import (
    MAX_RETAINED_THUMBNAILS,
    MAX_VISIBLE_THUMBNAILS,
    ThumbnailCoordinator,
)

pytestmark = pytest.mark.core


class FakeServer:
    def __init__(self) -> None:
        self.counter = 0
        self.owned: set[str] = set()
        self.released: list[str] = []

    def publish_jpeg(self, _data: bytes) -> str:
        self.counter += 1
        url = f"http://127.0.0.1:50000/token/{self.counter}.jpg"
        self.owned.add(url)
        return url

    def retain_jpeg(self, url: str) -> bool:
        return url in self.owned

    def release_jpeg(self, url: str, force: bool = False) -> bool:
        self.owned.discard(url)
        self.released.append(url)
        return True


def _wait_for(predicate) -> bool:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


def test_visible_cap_and_invalid_path_rejected() -> None:
    coordinator = ThumbnailCoordinator(FakeServer(), lambda *_a, **_kw: {}, lambda *_a: None)
    try:
        with pytest.raises(ValueError):
            coordinator.request([str(i) for i in range(MAX_VISIBLE_THUMBNAILS + 1)])
        with pytest.raises(ValueError):
            coordinator.request([""])
        assert coordinator.request([]) == {}
    finally:
        coordinator.close()


def test_cached_thumbnails_reused_with_bounded_server_retention() -> None:
    server = FakeServer()
    notifications: list[dict] = []
    coordinator = ThumbnailCoordinator(
        server,
        lambda *_a, **_kw: {"status": "success", "jpeg_bytes": b"jpeg"},
        lambda _evt, payload, _id: notifications.append(payload),
    )
    try:
        for i in range(MAX_RETAINED_THUMBNAILS + 4):
            path = f"/art/{i}.png"
            coordinator.request([path])
            assert _wait_for(lambda p=path: any(msg["path"] == p for msg in notifications))
        assert len(server.owned) <= MAX_RETAINED_THUMBNAILS
        assert server.released
        assert coordinator.request([f"/art/{MAX_RETAINED_THUMBNAILS + 3}.png"])
    finally:
        coordinator.close()
    assert not server.owned


def test_new_visible_set_discards_stale_worker_result() -> None:
    started = threading.Event()
    resume = threading.Event()
    received: list[str] = []

    def render(path, _config, **_kwargs):
        if path == "old":
            started.set()
            assert resume.wait(2)
        return {"status": "success", "jpeg_bytes": b"data"}

    coordinator = ThumbnailCoordinator(
        FakeServer(), render, lambda _event, payload, _id: received.append(payload["path"])
    )
    try:
        coordinator.request(["old"])
        assert started.wait(2)
        coordinator.request(["new"])
        resume.set()
        assert _wait_for(lambda: "new" in received)
        assert "old" not in received
    finally:
        resume.set()
        coordinator.close()


def test_failed_thumbnail_is_not_retried_on_every_render() -> None:
    rendered: list[str] = []
    failed = []

    def render(path, _config, **_kwargs):
        rendered.append(path)
        return {"status": "error", "error": "unsupported"}

    coordinator = ThumbnailCoordinator(
        FakeServer(), render, lambda _event, payload, _id: failed.append(payload)
    )
    try:
        coordinator.request(["unsupported"])
        assert _wait_for(lambda: len(failed) == 1)
        coordinator.request(["unsupported"])
        time.sleep(0.03)
        assert rendered == ["unsupported"]
    finally:
        coordinator.close()


def test_age_expiry_releases_old_handle_and_queues_fresh_thumbnail() -> None:
    server = FakeServer()
    completed: list[dict] = []
    coordinator = ThumbnailCoordinator(
        server,
        lambda *_a, **_kw: {"status": "success", "jpeg_bytes": b"jpeg"},
        lambda _event, payload, _op: completed.append(payload),
    )
    try:
        coordinator.request(["/art/sample.png"])
        assert _wait_for(lambda: len(completed) == 1)
        first = completed[0]["url"]
        assert coordinator.request(["/art/sample.png"])["/art/sample.png"] == first
        with coordinator._lock:
            old_url, cached_at = coordinator._cache["/art/sample.png"]
            coordinator._cache["/art/sample.png"] = (old_url, cached_at - 300)
        assert coordinator.request(["/art/sample.png"]) == {}
        assert _wait_for(lambda: len(completed) == 2)
        assert first in server.released
        assert completed[1]["url"] != first
    finally:
        coordinator.close()
