"""Bounded gallery thumbnails using the existing isolated preview worker slot.

Only currently visible files are eligible for work. One background render,
a fixed-size LRU, no directory traversal, and no work on the JS bridge thread.
Thumbnails use neutral preview settings rather than live inspector adjustments.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

MAX_VISIBLE_THUMBNAILS = 16
MAX_RETAINED_THUMBNAILS = 20
THUMBNAIL_MAX_DIMENSION = 192
THUMBNAIL_RENDER_TIMEOUT = 6.0
THUMBNAIL_CACHE_TTL_SECONDS = 240.0


class ThumbnailServer(Protocol):
    def publish_jpeg(self, data: bytes) -> str: ...
    def retain_jpeg(self, handle: str) -> bool: ...
    def release_jpeg(self, handle: str, force: bool = False) -> bool: ...


class ThumbnailCoordinator:
    """A single latest-visible request set and bounded session LRU."""

    def __init__(
        self,
        server: ThumbnailServer,
        render: Callable[..., dict[str, Any]],
        dispatch: Callable[[str, dict[str, Any], str], None],
    ) -> None:
        self._server = server
        self._render = render
        self._dispatch = dispatch
        self._lock = threading.Lock()
        self._wanted: tuple[str, ...] = ()
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._failed: set[str] = set()
        self._thread: threading.Thread | None = None
        self._closed = False

    def is_busy(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def request(self, paths: list[str]) -> dict[str, str]:
        """Return cached URLs; queue only missing visible assets."""
        if len(paths) > MAX_VISIBLE_THUMBNAILS:
            raise ValueError(f"Too many visible thumbnails (limit {MAX_VISIBLE_THUMBNAILS})")
        if any(not isinstance(path, str) or not path for path in paths):
            raise ValueError("Invalid thumbnail source path")
        paths = list(dict.fromkeys(paths))
        with self._lock:
            if self._closed:
                raise RuntimeError("Thumbnail service is shutting down")
            self._wanted = tuple(paths)
            self._failed.intersection_update(paths)
            hits = {}
            now = time.monotonic()
            for path in paths:
                cached = self._cache.get(path)
                if cached is not None and now - cached[1] >= THUMBNAIL_CACHE_TTL_SECONDS:
                    self._cache.pop(path)
                    self._server.release_jpeg(cached[0], force=True)
                    cached = None
                if cached is not None:
                    self._cache.move_to_end(path)
                    hits[path] = cached[0]
            if paths and self._thread is None and any(
                path not in self._cache and path not in self._failed for path in paths
            ):
                self._thread = threading.Thread(target=self._work, name="previewgen-thumb", daemon=True)
                self._thread.start()
            return hits

    def _work(self) -> None:
        while True:
            with self._lock:
                if self._closed:
                    self._thread = None
                    return
                path = next(
                    (p for p in self._wanted if p not in self._cache and p not in self._failed), None
                )
                if path is None:
                    # Reset under the lock. A concurrent request can now spawn
                    # a new worker rather than losing its last update.
                    self._thread = None
                    return
            try:
                # Deliberately omit user overlays and expensive per-asset
                # inspector changes from gallery navigation thumbnails.
                result = self._render(
                    path, {"text": "", "opacity": 0, "logoPath": ""},
                    max_dimension=THUMBNAIL_MAX_DIMENSION,
                    timeout_seconds=THUMBNAIL_RENDER_TIMEOUT,
                )
                if result.get("status") != "success":
                    raise RuntimeError(str(result.get("error") or "Thumbnail unavailable"))
                data = result.get("jpeg_bytes")
                if not isinstance(data, bytes) or not data:
                    raise ValueError("Empty thumbnail image")
                with self._lock:
                    if self._closed or path not in self._wanted:
                        continue
                    url = self._server.publish_jpeg(data)
                    if not self._server.retain_jpeg(url):
                        self._server.release_jpeg(url, force=True)
                        raise RuntimeError("Could not retain thumbnail")
                    self._cache[path] = (url, time.monotonic())
                    self._cache.move_to_end(path)
                    while len(self._cache) > MAX_RETAINED_THUMBNAILS:
                        _, old = self._cache.popitem(last=False)
                        self._server.release_jpeg(old[0], force=True)
                self._dispatch("thumbnail.ready", {"path": path, "url": url}, "thumbnail")
            except Exception as exc:
                logging.debug("Thumbnail unavailable for selected asset: %s", exc)
                with self._lock:
                    if self._closed:
                        self._thread = None
                        return
                    self._failed.add(path)
                self._dispatch("thumbnail.failed", {"path": path}, "thumbnail")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._wanted = ()
            old_urls = [entry[0] for entry in self._cache.values()]
            self._cache.clear()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.4)
        for url in old_urls:
            self._server.release_jpeg(url, force=True)
